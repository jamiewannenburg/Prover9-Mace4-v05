#     Copyright (C) 2007 William McCune
#
#     This file is part of the LADR Deduction Library.
#
#     The LADR Deduction Library is free software; you can redistribute it
#     and/or modify it under the terms of the GNU General Public License
#     as published by the Free Software Foundation; either version 2 of the
#     License, or (at your option) any later version.
#
#     The LADR Deduction Library is distributed in the hope that it will be
#     useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with the LADR Deduction Library; if not, write to the Free Software
#     Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
#

# system imports

import os, sys, re
import wx

# local imports

from platforms import Win32, Mac

"""
The State class simplifies handling states of objects (e.g. jobs).
"""

class State:
    not_started = 'not_started'
    ready = 'ready'
    running = 'running'
    suspended = 'suspended'
    finished = 'finished'
    failed = 'failed'
    error = 'error'

def error_dialog(message, caption='Error'):
    dlg = wx.MessageDialog(None, message, caption, wx.OK|wx.ICON_ERROR)
    dlg.ShowModal()
    dlg.Destroy()    

def info_dialog(message, caption='Information'):
    dlg = wx.MessageDialog(None, message, caption, wx.OK|wx.ICON_INFORMATION)
    dlg.ShowModal()
    dlg.Destroy()    

"""
Find the top Window of a wx hierarchy.
"""
def to_top(w):
    if isinstance(w, wx.Window):
        p = w.GetParent()
        if p:
            return to_top(p)
        else:
            return w

def size_that_fits(size_required, percent_of_screen = 0.85):
    """
    Try to give the requested size, but make sure it can fit on the screen.
    (size is (width,height))
    """
    (frame_width,frame_height) = size_required
    screen_width = wx.GetDisplaySize()[0] * percent_of_screen
    screen_height = wx.GetDisplaySize()[1] * percent_of_screen

    if frame_width > screen_width:
        frame_width = screen_width
    if frame_height > screen_height:
        frame_height = screen_height
    return (int(frame_width), int(frame_height))

def pos_for_center(size):
    """
    Return a position that will center the window on the screen.
    """
    (frame_width,frame_height) = size
    screen_width = wx.GetDisplaySize()[0]
    screen_height = wx.GetDisplaySize()[1]

    x = screen_width//2 - frame_width//2
    y = screen_height//2 - frame_height//2
    return (x,y)

def screen_center():
    """
    Return the center of the screen.
    """
    screen_width = wx.GetDisplaySize()[0]
    screen_height = wx.GetDisplaySize()[1]
    return (screen_width//2, screen_height//2)

def max_width(str_list, wxfont):
    """
    Return the max width of a list of strings in the given font.
    """
    if str_list:
        dc = wx.ScreenDC()
        dc.SetFont(wxfont)
        widths = [dc.GetTextExtent(s)[0] for s in str_list]
        return max(widths)
    else:
        return 0

# Platform dependencies for wx.FileDialog

def open_dir_style(current_dir):
    """
    Directory and style arguments for wx.FileDialog to open files.
    """
    if current_dir:
        dir = os.path.dirname(current_dir)
    elif Mac():
        dir = os.path.expanduser('~')
    else:
        dir = os.path.abspath(os.path.curdir)
    style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
    return (dir,style)

def saveas_dir_style(current_dir):
    """
    Directory and style arguments for wx.FileDialog to save files.
    """
    if current_dir:
        dir = os.path.dirname(current_dir)
    elif Mac():
        dir = os.path.expanduser('~')
    else:
        dir = os.path.abspath(os.path.curdir)
    style = wx.FD_SAVE
    return (dir,style)

class Content_change:
    """
    An event handler can use this class to keep track of text highlighting.
    See the on_text_change method in the Formula_tab class for an example.
    """
    def __init__(self, t):
        """
        Create a Content_change event handler with timer t of the parent.
        (The parent must already have a timer instantiated.)
        """
        self.normal_color = 'BLACK'
        self.good_color = 'BLUE'
        self.bad_color = 'RED'
        self.last_edit_pos = 0
        self.prev_text = ''
        self.timer = t
        self.highlight_timer_id = None

    def highlight(self, tc, start, end, type='BLUE'):
        """
        Temporarily hilight text from start to end (or all if not given).
        Type can be one of the defined colors.
        The caller must assure the range is legal.
        """
        # first make sure all text is the normal color
        tc.SetStyle(0, tc.GetLastPosition(),
                    wx.TextAttr(self.normal_color, 'WHITE'))

        # now set the given range to type
        color = None
        if type == 'BLUE':
            color = self.good_color
        elif type == 'RED':
            color = self.bad_color

        if color:
            tc.SetStyle(start, end, wx.TextAttr(color, 'WHITE'))
            if self.highlight_timer_id == None:
                self.highlight_timer_id = wx.NewId()
                self.timer.Start(1500)  # 1.5 seconds

    def clear_highlight(self, tc):
        """
        Change all text to the normal color.
        """
        tc.SetStyle(0, tc.GetLastPosition(),
                    wx.TextAttr(self.normal_color, 'WHITE'))
        if self.highlight_timer_id != None:
            self.timer.Stop()
            self.highlight_timer_id = None

    def on_timer(self, tc, evt):
        """
        Handle a timer event.
        """
        if self.highlight_timer_id != None:
            self.clear_highlight(tc)

    def on_change(self, tc, evt):
        """
        Handle an EVT_TEXT event.
        """
        self.clear_highlight(tc)
        self.last_edit_pos = tc.GetInsertionPoint()

"""
A Frame for displaying text (output), with optional Save button.
"""

class Text_frame(wx.Frame):
    def __init__(self, parent, font, title, text='', saveas=True):
        """
        Create a Text_frame with given title and content.
        """
        size = size_that_fits((700,500))
        wx.Frame.__init__(self, parent, -1, title=title, size=size)
        panel = wx.Panel(self, -1)

        self.text = wx.TextCtrl(panel, -1, style=wx.TE_MULTILINE|wx.TE_READONLY)
        self.text.SetFont(font)
        self.text.write(text)

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(self.text, 1, wx.EXPAND|wx.ALL, 5)
        if saveas:
            hbox = wx.BoxSizer(wx.HORIZONTAL)

            b_save = wx.Button(panel, wx.ID_SAVE, 'Save As...')
            b_close = wx.Button(panel, wx.ID_CLOSE, 'Close')
            hbox.Add(b_save, 0, wx.RIGHT|wx.BOTTOM, 5)
            hbox.Add(b_close, 0, wx.RIGHT|wx.BOTTOM, 5)
            self.Bind(wx.EVT_BUTTON, self.on_save, id=wx.ID_SAVE)
            self.Bind(wx.EVT_BUTTON, self.on_close, id=wx.ID_CLOSE)
            
            vbox.Add(hbox, 0, wx.ALIGN_RIGHT|wx.RIGHT, 5)
        panel.SetSizer(vbox)
        panel.Layout()

    def on_save(self, evt):
        """
        Save the text to a file selected by the user.
        """
        dlg = wx.FileDialog(self, message='Save file as ...',
                            defaultDir=os.path.abspath(os.path.curdir),
                            style = wx.FD_SAVE)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()  # full path
            try:
                dfile = os.path.basename(path)
                dfile = re.sub(r'\.[^.]*$', '', dfile)  # get rid of any extension
                self.SetTitle(dfile)

                f = open(path, 'w')
                f.write(self.text.GetValue())
                f.close()
            except IOError as e:
                error_dialog('Error opening file %s for writing.' % path)
            
        dlg.Destroy()

    def on_close(self, evt):
        self.Destroy()

class Invoke_event(wx.PyEvent):
    """Simple event to carry arbitrary result data."""
    def __init__(self, data):
        """Init Result Event."""
        wx.PyEvent.__init__(self)
        self.SetEventType(wx.NewId())
        self.data = data

"""
Busy_bar class.  This is a  busy meter, not a progress meter.
It doesn't tell you now much of the job is done (because we
don't know).  It just lets you know that the program is
working on the job.
"""

class Busy_bar(wx.Gauge):
    def __init__(self, parent, range=50, delay=100):
        """
        Initialize a busy bar.
          range: Number of intervals (arbitrary); doesn't represent percentage.
          delay: Timer interval in milliseconds.
        """
        wx.Gauge.__init__(self, parent, -1, range=range, size=(250, 20))
        
        self.range = range
        self.state = 0
        self.delay = delay
        self.timer = None
        self.forward = True
        self.value = 0
        self.SetValue(0)

    def start(self):
        """
        Start the timer, which moves the indicator back and forth.
        """
        # start timer
        if self.timer == None:
            self.timer = wx.Timer(self, -1)
            # Replace deprecated EVT_TIMER with Bind
            self.Bind(wx.EVT_TIMER, self.update_bar, self.timer)
            self.timer.Start(self.delay)  # milliseconds

    def stop(self):
        """
        Stop the timer and reset the indicator to 0.
        """
        if self.timer != None:
            self.timer.Stop()
            self.timer = None
            self.SetValue(0)

    def update_bar(self, evt):
        if self.forward:
            self.value += 1
            if self.value >= self.range:
                self.value = self.range
                self.forward = False
        else:
            self.value -= 1
            if self.value <= 0:
                self.value = 0
                self.forward = True
        self.SetValue(self.value)

class Mini_info:
    """
    Mini-display (StaticText) for info or warning messages.
    When give_info is called, the message is displayed.
    A call to clear_info clears the message.
    """
    def __init__(self, parent, text=''):
        self.st = wx.StaticText(parent, -1, text)

    def give_info(self, text, info_color=wx.RED):
        self.st.SetLabel(text)
        self.st.SetForegroundColour(info_color)
        p = self.st.GetParent()
        w = p.GetParent()
        w.Layout()

    def clear_info(self):
        self.st.SetLabel('')
        p = self.st.GetParent()
        w = p.GetParent()
        w.Layout()

