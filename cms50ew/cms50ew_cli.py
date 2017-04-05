#!/usr/bin/env python3

import argparse
import curses
import cms50ew
import sys
import time
import datetime
import signal
import bluetooth
import dateutil.parser as duparser

def main(stdscr):
    """Sets up a curses screen."""
    
    if not args.raw:
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.curs_set(0)
        stdscr.nodelay(1)
    
        global stdscr_height
        stdscr_height = stdscr.getmaxyx()[0]
    
    def no_data(status, finger):
        """Updates screen when no data is available."""

        if not args.raw:
            stdscr.clear()
            stdscr.addstr(0, 0, 'Pulse rate: ')
            stdscr.addstr('n/a', curses.A_BOLD)
            stdscr.addstr(1, 0, 'SpO2: ')
            stdscr.addstr('n/a', curses.A_BOLD)
            stdscr.addstr(2, 0, 'Status: ')
            stdscr.addstr(status, curses.A_BLINK)
            stdscr.addstr(stdscr_height - 1, 0, "Press 'q' to quit")
            stdscr.refresh()
        else:
            if status == oxi.old_status:
                pass # No change -> no output
            else:
                print(finger, 0, 0)
                oxi.old_status = status
        
    def data_update(status, finger, pulse_rate, spo2):
        """Updates screen"""
        if not args.raw:
            stdscr.clear()
            stdscr.addstr(0, 0, 'Pulse rate: ')
            stdscr.addstr(str(pulse_rate), curses.color_pair(1) | curses.A_BOLD)
            stdscr.addstr(' bpm')
            stdscr.addstr(1, 0, 'SpO2: ')
            stdscr.addstr(str(spo2), curses.color_pair(2) | curses.A_BOLD)
            stdscr.addstr(' %')
            stdscr.addstr(2, 0, 'Status: ')
            stdscr.addstr(status)
            stdscr.addstr(stdscr_height - 1, 0, "Press 'q' to quit")
            stdscr.refresh()
        else:
            if pulse_rate == oxi.old_pulse_rate and spo2 == oxi.old_spo2:
                pass # No change -> no output
            else:
                print(finger, pulse_rate, spo2)
                oxi.old_pulse_rate = pulse_rate
                oxi.old_spo2 = spo2

    def init_live_data():
        """Initiates live data feed and keeps it alive."""
        if args.raw: # Initiate variables to hold old values
            oxi.old_pulse_rate = -1
            oxi.old_spo2 = -1
            oxi.old_status = 'No status'
        oxi.starttime = time.time()
        while True:
            oxi.initiate_device()
            oxi.send_cmd(oxi.cmd_get_live_data)
            try:
                update_live_data()
            except (TypeError, bluetooth.btcommon.BluetoothError):
                # Every once in a while (every ~30 seconds) the data stream
                # interrupts for reasons unknown. So we just restart.
                pass
        
    def update_live_data():
        """Gets, stores and displays live data from oximeter instance."""
        finger_out = False
        low_signal_quality = False
        global stdscr_height
        counter = 0
        
        while True:
            data = oxi.process_data()
            finger = data[0]
            pulse_rate = data[1]
            spo2 = data[2]
            
            # Store live session data in object once every second
            oxi.timer = time.time()
            delta_time = oxi.timer - oxi.starttime
            if not oxi.stored_data: # Might still be empty
                if delta_time > 1:
                    oxi.stored_data.append([round(delta_time), finger, pulse_rate, spo2])
            else:
                if delta_time - oxi.stored_data[-1][0] > 1: # Save one data set per sec
                    oxi.stored_data.append([round(delta_time), finger, pulse_rate, spo2])
            
            if not args.raw:
                c = stdscr.getch()
                if c == ord('q'):
                    exit_nicely(0, 0)
                elif c == curses.KEY_RESIZE:
                    stdscr_height = stdscr.getmaxyx()[0]
                
            if finger == 'Y':
                # The counter > n condition serves to suppress hiccups where
                # the oximeter reports "Finger out" when it isn't.
                if not finger_out and counter > 10:
                    no_data('Finger out', finger)
                    finger_out = True
                    low_signal_quality = False
                    counter = 0
                elif not finger_out and counter < 11:
                    counter += 1
            elif (pulse_rate == 0) or (spo2 == 0):
                    no_data('Low signal quality', finger)
                    finger_out = False
                    low_signal_quality = True
            else:
                data_update('Processing data', finger, pulse_rate, spo2)
                finger_out = False
                low_signal_quality = False
    
    # Set up an oximeter instance and initiate live data stream
    if not oxi.setup_device(target=args.device, is_bluetooth=args.bluetooth):
        print('Connection attempt unsuccessful.')
        sys.exit(1)
    if args.datetime:
        oxi.pydatetime = datetime.datetime.now()
    init_live_data()

def exit_nicely(signal, frame):
    if args.datetime:
        oxi.convert_datetime()
    if args.csv:
        print('\nSaving live session data to: ' + str(args.csv) + ' ...')
        oxi.write_csv(args.csv)
    if args.pygal:
        print('Plotting downloaded data with Pygal and saving plot to: ' + str(args.pygal) + ' ...')
        oxi.plot_pygal()
        oxi.write_svg(args.pygal)
    if args.mpl:
        print('Plotting downloaded data with Matplotlib and displaying it ...')
        oxi.plot_mpl()
    print('Closing device ...')
    oxi.close_device()
    sys.exit(0)

def live():
    """Starts curses interface with live stream if action argument is 'live'"""
    
    if not args.raw:
        curses.wrapper(main)
    else:
        main(0)
    
def download():
    """Function to deal with 'download' action argument"""
    oxi = cms50ew.CMS50EW()
    print('Connecting to device ' + str(args.device) + ' ...')
    if not oxi.setup_device(target=args.device, is_bluetooth=args.bluetooth):
        raise Exception('Connection attempt unsuccessful.')
    oxi.initiate_device()
    oxi.get_session_count()
    if oxi.sess_available == 'No':
        raise Exception('No stored session data available.')
    oxi.get_session_duration()
    oxi.send_cmd(oxi.cmd_get_session_data)
    counter = 1
    while oxi.download_data():
        print('Downloading data point ' + str(counter) + ' of ' + str(oxi.sess_data_points))
        counter += 1
    print('Downloaded data points:', len(oxi.stored_data))
    
    if args.datetime:
        try:
            oxi.pydatetime = duparser.parse(args.datetime)
        except ValueError:
            raise argparse.ArgumentTypeError('No valid date format')
        else:
            oxi.convert_datetime()
            
    if args.csv:
        print('Saving downloaded data to: ' + str(args.csv) + ' ...')
        oxi.write_csv(args.csv)
    
    if args.pygal:
        print('Plotting downloaded data with Pygal and saving plot to: ' + str(args.pygal) + ' ...')
        oxi.plot_pygal()
        oxi.write_svg(args.pygal)
    
    if args.mpl:
        print('Plotting downloaded data with Matplotlib and displaying it ...')
        oxi.plot_mpl()

# Main parser
parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers(help='specify action to perform', dest='action')
subparsers.required = True

# Parser for 'live' action argument
parser_live = subparsers.add_parser('live', help='display live data in curses UI')
parser_live.set_defaults(func=live)
parser_live.add_argument('-b', '--bluetooth', 
                         help='specify if connection is to be established via Bluetooth (default is serial)', action='store_true')
parser_live.add_argument('-r', '--raw', help='use raw mode, i.e. print live data in a script-friendly manner as "<Finger out> <Pulse rate> <SpO2>"', action='store_true')
parser_live.add_argument('--csv', metavar='file', help='store live session data in CSV file')
parser_live.add_argument('--pygal', metavar='file', help='plot live data with Pygal and store it as SVG')
parser_live.add_argument('--mpl', help='plot live data with Matplotlib and display it',
                             action='store_true')
parser_live.add_argument('--datetime', help='use current time as start time for stored live session data', action='store_true')
parser_live.add_argument('device', help='specify serial port or MAC address of Bluetooth device')

# Parser for 'download' action argument
parser_download = subparsers.add_parser('download', help='download stored session data')
parser_download.set_defaults(func=download)
parser_download.add_argument('-b', '--bluetooth', 
                             help='specify if connection is to be established via Bluetooth (default is serial)', action='store_true')
parser_download.add_argument('device', 
                             help='specify serial port or MAC address of Bluetooth device')
parser_download.add_argument('--csv', metavar='file', help='store saved data in CSV file')
parser_download.add_argument('--pygal', metavar='file', help='plot data with Pygal and store it as SVG')
parser_download.add_argument('--mpl', help='plot data with Matplotlib and display it',
                             action='store_true')
parser_download.add_argument('--datetime', help='specify start time of recording, e.g. 16 Mar 2017 22:30')

# Parse arguments
args = parser.parse_args()

# Set up an oximeter instance and introduce signal handling
oxi = cms50ew.CMS50EW()
signal.signal(signal.SIGINT, exit_nicely)

# Run action function
args.func()
