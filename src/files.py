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

import os, sys
import importlib.util
import importlib.machinery

# local imports

from platforms import Win32, Mac, Mac_ppc

def path_info():
    info = ('os.getcwd(): %s\n'
            'sys.argv[0]: %s\n'
            'sys.path[0]: %s\n'
            'os.path.dirname(sys.executable): %s'
            'os.path.dirname(os.path.abspath(sys.argv[0])): %s' %
            (os.getcwd(),
             sys.argv[0],
             sys.path[0],
             os.path.dirname(sys.executable),
             os.path.dirname(os.path.abspath(sys.argv[0])),
            ))
    return info

def program_dir():
    """
    This gets the full pathname of the directory containing the program.
    It is used for referring to other files (binaries, images, etc.).
    """
    if (Win32() and (hasattr(sys, 'frozen') or importlib.machinery.FrozenImporter.find_spec('__main__') is not None)):
        # running from exe generated by py2exe
        return os.path.dirname(sys.executable)
    else:
        return sys.path[0]
        # return os.path.dirname(os.path.abspath(sys.argv[0]))

def bin():
    if Win32():
        return 'bin-win32'
    elif Mac():
        if Mac_ppc():
            return 'bin-mac-ppc'
        else:
            return 'bin-mac-intel'
    else:
        return 'bin'

def bin_dir():
    return os.path.join(program_dir(), bin())

def image_dir():
    return os.path.join(program_dir(), 'Images')

def sample_dir():
    return os.path.join(program_dir(), 'Samples')

def binary_ok(fullpath):
    if not fullpath:
        return False
    elif Win32():
        return os.access(fullpath + '.exe', os.X_OK)
    else:
        return os.access(fullpath, os.X_OK)

