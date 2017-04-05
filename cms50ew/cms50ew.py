#!/usr/bin/env python3

import serial
import bluetooth
import glob
import datetime
import pygal
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import csv

class CMS50EW():
    """Class to instantiate a CMS50EW pulse oximeter."""
    def __init__(self):
        self.pulse_xdata, self.pulse_ydata, self.spo2_xdata, self.spo2_ydata, self.finger_data = [[0], [0], [0], [0], ['Y']]
        self.x_label = 'Time [s]' # Define x-axis label for plots
        self.x_values = []
        self.plot_title = 'Saved session'
        self.n_data_points = 0
        self.timer = 0
        self.starttime = 0
        self.stored_data = []
        self.stored_data_time = 0
        # Most of the following commands we don't use. They are just there as
        # some sort of documentation
        self.cmd_hello1 = b'\x7d\x81\xa7\x80\x80\x80\x80\x80\x80'
        self.cmd_hello2 = b'\x7d\x81\xa2\x80\x80\x80\x80\x80\x80'
        self.cmd_hello3 = b'\x7d\x81\xa0\x80\x80\x80\x80\x80\x80'
        self.cmd_session_hello = b'\x7d\x81\xad\x80\x80\x80\x80\x80\x80'
        self.cmd_get_session_count = b'\x7d\x81\xa3\x80\x80\x80\x80\x80\x80'
        self.cmd_get_session_time = b'\x7d\x81\xa5\x80\x80\x80\x80\x80\x80'
        self.cmd_get_session_duration = b'\x7d\x81\xa4\x80\x80\x80\x80\x80\x80'
        self.cmd_get_user_info = b'\x7d\x81\xab\x80\x80\x80\x80\x80\x80'
        self.cmd_get_session_data = b'\x7d\x81\xa6\x80\x80\x80\x80\x80\x80'
        self.cmd_get_deviceid = b'\x7d\x81\xaa\x80\x80\x80\x80\x80\x80'
        self.cmd_get_info = b'\x7d\x81\xb0\x80\x80\x80\x80\x80\x80'
        self.cmd_get_model = b'\x7d\x81\xa8\x80\x80\x80\x80\x80\x80'
        self.cmd_get_vendor = b'\x7d\x81\xa9\x80\x80\x80\x80\x80\x80'
        self.cmd_session_erase = b'\x7d\x81\xae\x80\x80\x80\x80\x80\x80'
        self.cmd_custom = b'\x7d\x81\xf5\x80\x80\x80\x80\x80\x80'
        self.cmd_session_stuff = b'\x7d\x81\xaf\x80\x80\x80\x80\x80\x80'
        self.cmd_get_live_data = b'\x7d\x81\xa1\x80\x80\x80\x80\x80\x80'
        
    def setup_device(self, target, is_bluetooth=False):
        self.target = target
        self.is_bluetooth = is_bluetooth
        if self.is_bluetooth:
            self.btsock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            try:
                self.btsock.connect((self.target, 1))
            except:
                #print('BT connection failed')
                return False
            else:
                #print('BT connection successful.')
                # Might be better to solve this via select for recv only:
                # http://stackoverflow.com/questions/2719017/how-to-set-timeout-on-pythons-socket-recv-method
                self.btsock.settimeout(1)
                return True
        else:
            self.ser = serial.Serial(self.target,
                                     baudrate = 115200,
                                     parity = serial.PARITY_NONE,
                                     stopbits = serial.STOPBITS_ONE,
                                     bytesize = serial.EIGHTBITS,
                                     timeout = 0.1,
                                     xonxoff = 1)
            return True
            
    def initiate_device(self):
        """Sends bytes to device which seem to serve its initialization."""
        self.send_cmd(self.cmd_hello1)
        response = self.recv()
        if not response:
            return False
        self.send_cmd(self.cmd_hello2)
        self.send_cmd(self.cmd_hello3)
        self.recv()
        return True
        
    def recv(self, bytes=1):
        """Receives entire response from device and saves it in list."""
        response_list = []
        while True:
            if self.is_bluetooth:
                try:
                    response = self.btsock.recv(bytes)
                except bluetooth.btcommon.BluetoothError:
                    response = False
            else:
                response = self.ser.read()
                
            if response:
                response_list.append(response)
            else:
                break
        return response_list
        
    def send_cmd(self, cmd, debug=False):
        """
        Sends specified command to device and prints debug output if debug flag
        is set.
        """
        if self.is_bluetooth:
            self.btsock.send(cmd)
        else:
            self.ser.write(cmd)
        
        if debug:
            print("Write:    ", cmd)
            response = []
            while True:
                r = response.append(self.ser.read())
                if self.ser.in_waiting == 0:
                    break
            response_string = ' '.join([str(ord(r)) for r in response])
            print("Response: ", response)
            
    def get_session_count(self):
        """Checks if stored data is available and stores result in self.sess_available."""
        self.send_cmd(self.cmd_get_session_count)
        response = self.recv()
        
        session_count = ord(response[3]) & 0x7f
        if session_count == 1:
            self.sess_available = 'Yes'
        else:
            self.sess_available = 'No'
    
    def get_session_duration(self):
        """Retrieves session duration, calculates data points"""
        self.send_cmd(self.cmd_get_session_duration)
        response = self.recv()
        
        response_conv = []
        for r in response:
            response_conv.append(ord(r) & 0x7f)
            
        # I got the following logic from Mark Watkins' SleepyHead
        duration = ((response_conv[1] & 0x04) << 5)
        duration |= response_conv[4]
        duration |= (response_conv[5] | ((response_conv[1] & 0x08) << 4)) << 8
        duration |= (response_conv[6] | ((response_conv[1] & 0x10) << 3)) << 16
        
        duration_seconds = duration / 2
        self.sess_duration = datetime.timedelta(seconds=duration_seconds)
        self.sess_data_points = round(self.sess_duration.total_seconds() / 3)
        
    def get_vendor(self):
        """Retrieves vendor and stores it in self.vendor."""
        self.send_cmd(self.cmd_get_vendor)
        response = self.recv()
        self.vendor = ''.join([chr(ord(r) & 0x7f) for r in response if chr(ord(r) & 0x7f).isalnum()])
    
    def get_model(self):
        """Retrieves model and stores it in self.model."""
        self.send_cmd(self.cmd_get_model)
        response = self.recv()
        self.model = ''.join([chr(ord(r) & 0x7f) for r in response if chr(ord(r) & 0x7f).isalnum()])
        
    def get_user(self):
        """Retrieves user and stores it in self.user."""
        self.send_cmd(self.cmd_get_user_info)
        response = self.recv()
        self.user = ''.join([chr(ord(r) & 0x7f) for r in response if chr(ord(r) & 0x7f).isalnum()])
                        
    def process_data(self):
        """Reads data from device and returns key values."""
        counter = 1
        value_list = []
        while counter < 9:
            if self.is_bluetooth:
                value = self.btsock.recv(1)
            else:
                value = self.ser.read()
            # The following if clause basically functions to discard the first
            # bunch of data  which is of no use to us; the list of values we
            # need starts with a 1.
            
            if ord(value) == 1:
                value_list = []
                counter = 1
            else:
                counter += 1
            value_list.append(value)
        
        # Extract the key values from value_list
        finger = value_list[3]
        if finger == b'\xc0':
            finger = 'Y'
        else:
            finger = 'N'
        pulse_rate = int(ord(value_list[5]) & 0x7f)
        spo2 = int(ord(value_list[6]) & 0x7f)
        
        return [finger, pulse_rate, spo2]
    
    def download_data(self):
        """
        Downloads stored session data from device one value at a time to allow
        the UI's control over this process. The results are stored in self.data_stored
        Another possibility would be to implement the download process fully here and
        have the progress checked regularly via len(self.stored_data) by the UI.
        """
        try: 
            data = self.process_data()
        except (TypeError, bluetooth.btcommon.BluetoothError): # These exceptions are raised when there is no data left to download
            self.stored_data_time = 0 # Reset the timer
            print('No data left to download')
            return False
        else:
            data.insert(0, self.stored_data_time)
            self.stored_data.append(data)
            self.stored_data_time += 3 # A data point is stored every three seconds
            return True
        
    def convert_datetime(self):
        """Replaces time deltas with absolute time."""
        for data in self.stored_data:
            newtime = self.pydatetime + datetime.timedelta(0, data[0])
            self.x_values.append(data[0]) # Copy original values for Matplotlib
            data[0] = newtime.time().strftime('%H:%M:%S')
        self.x_label = 'Time'
        enddatetime = self.pydatetime + datetime.timedelta(0, self.x_values[-1])
        self.plot_title = str('Recorded session from ' + 
                                   self.pydatetime.strftime('%d %B %Y, %H:%M:%S') + ' to ' 
                                   + enddatetime.strftime('%d %B %Y, %H:%M:%S'))
        
    def write_csv(self, filename):
        """Writes session data as CSV file."""
        with open(filename, 'w') as f:
            datawriter = csv.writer(f, delimiter=',')
            datawriter.writerow([self.x_label, 'Finger out', 'Pulse rate [bpm]', 'SpO2 [%]'])
            datawriter.writerows(self.stored_data)
    
    def close_device(self):
        """Closes device socket"""
        if self.is_bluetooth:
            self.btsock.close()
        else:
            self.ser.close()
    
    def plot_pygal(self, live=False):
        """Plots stored session data as Pygal line chart."""

        if live:
            x_labels_every = int(round((len(self.stored_data) / 10)))
        else:
            # Show only approximately 10 labels
            x_labels_every = int(round((len(self.stored_data) / 10), -1))
            # Round to nearest multiple of 30 to get nice numbers (recorded data
            # consists of a data point every 3 seconds)
            x_labels_every = x_labels_every - (x_labels_every % 30)
        x_labels = []
        # Pygal's major labels feature is used to display a reasonable amount of labels
        x_labels_major = []
        x_labels_n = 0 # First data point is at 0 seconds
        for time in [data[0] for data in self.stored_data]:
            if x_labels_n != x_labels_every:
                x_labels_major.append(None)
                x_labels_n += 1
            else:
                if live and self.x_label == 'Time [s]':
                    x_labels_major.append(round(time, 1))
                else:
                    x_labels_major.append(time)
                x_labels_n = 1
            if live and self.x_label == 'Time [s]':
                x_labels.append(round(time, 1))
            else:
                x_labels.append(time)
                
        line_chart = pygal.Line(truncate_label=-1, 
                                x_title=self.x_label, 
                                show_minor_x_labels=False, 
                                range=(0, 260), 
                                secondary_range=(0, 100))
        line_chart.title = self.plot_title
        line_chart.x_labels = x_labels
        line_chart.x_labels_major = x_labels_major
        line_chart.add('Pulse [bpm]', [data[2] for data in self.stored_data])
        line_chart.add('SpO2 [%]', [data[3] for data in self.stored_data], secondary=True)
        
        self.chart = line_chart.render(width=1800)
        
    def plot_mpl(self):
        """Plots stored session data as Matplotlib plot."""
        fig, pulse_plot = plt.subplots(figsize=(15,10))
        
        if self.x_label == 'Time':
            xvalues = []
            for value in self.x_values:
                newdatetime = self.pydatetime + datetime.timedelta(0, value)
                xvalues.append(newdatetime)
        else:
            xvalues = [data[0] for data in self.stored_data]

        pulse_plot.plot(xvalues, [data[2] for data in self.stored_data], c='red')
        pulse_plot.set_title(self.plot_title, fontsize=24)
        pulse_plot.set_xlabel(self.x_label, fontsize=24)
        pulse_plot.set_ylabel('Pulse rate [bpm]', color='red', fontsize=20)
        pulse_plot.set_ylim([0, 220])

        spo2_plot = pulse_plot.twinx()
        spo2_plot.plot(xvalues, [data[3] for data in self.stored_data], c='blue')
        spo2_plot.set_ylabel('SpO2 [%]', color='blue', fontsize=20)
        spo2_plot.set_ylim([0, 100])

        pulse_plot.tick_params(axis='both', labelsize=16)
        spo2_plot.tick_params(axis='both', labelsize=16)
        
        if self.x_label == 'Time':
            fig.autofmt_xdate()
            pulse_plot.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        
        plt.show()
        
    def write_svg(self, filename):
        """Writes Pygal plot as SVG."""
        with open(filename, 'wb') as file:
            file.write(self.chart)
    
    def open_csv(self, filename):
        """Opens and processes CSV session file."""
        with open(filename, 'r') as file:
            reader = csv.reader(file)
            next(reader) # Skip header
            self.stored_data = []
            for row in reader:
                self.stored_data.append([float(row[0]), row[1], int(row[2]), int(row[3])])
        if (len(self.stored_data)) > 1:
            self.sess_available = 'Yes'
            self.sess_duration = datetime.timedelta(seconds=self.stored_data[-1][0])
        else:
            self.sess_available = 'No'
        
    def erase_session(self):
        """
        Erases the stored session from the device.
        Doesn't work right now.
        """
        self.send_cmd(self.cmd_session_erase)
        print('Sent erase command')
        
class DeviceScan():
    """Scans for serial or Bluetooth devices."""
    def __init__(self, is_bluetooth=False):
        if is_bluetooth:
            self.devices_dict = {}
            self.get_bt_devices()
        else:
            self.accessible_ports = []
            self.get_serial_ports()

    def get_bt_devices(self):
        """
        Scans for Bluetooth devices, looks up their name and returns a dictionary with both
        the devices' MAC address and name.
        """
        devices_addr = bluetooth.discover_devices()
        for address in devices_addr:
            device_name = bluetooth.lookup_name(address)
            self.devices_dict = {address:device_name}

    def get_serial_ports(self):
        """
        Tries to access serial ports and returns them as a list if successful.
        """
        available_ports = glob.glob('/dev/tty[A-Za-z]*')
    
        for port in available_ports:
            try:
                s = serial.Serial(port)
                self.accessible_ports.append(port)
                s.close()
            except serial.SerialException:
                pass
