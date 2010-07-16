#!/usr/bin/env python

# -*- coding: utf-8 -*-

""" An error display and reporting dialog.

Displays an error message whenever hatta trhows and unexpected exception. Sends 
tracebacks via e-mail.
"""
import sys, os, locale
import pprint

from PyQt4.QtGui import QDialog
from PyQt4.QtCore import (QString, QThread, pyqtSignal, pyqtSlot, Qt,
    QPoint, QLocale)

from ui_errorDialog import Ui_ErrorDialog

def pformat(object, indent=4, width=72, depth=10):
    if hasattr(object, 'keys') and hasattr(object, 'values'):
        return '{ ' + ('\n' + indent * ' ').join('%s:\t%s' %
                                (key, pformat(value, indent, width, depth))
                         for key, value in object.iteritems())
        + ' }'
    return pprint.pformat(object, indent, width, depth)

class ErrorDialog(QDialog, Ui_ErrorDialog):
    """ Extends the UI with connectivity. """
    def __init__(self):
        QDialog.__init__(self)
        self.setupUi(self)

        self._caption = None
        self._traceback = None

        self.details_button.toggled.connect(self._details_toggled)

    def _get_environment(self):
        """ Gathers as much data as possible about the execution einvroment. 
        """
        env = []
        env.append(('Platform', sys.platform))
        try:
            import sysconfig
            env.append(('Sysconfig', sysconfig.platform))
        except ImportError:
            try:
                env.append(('Uname', os.uname()))
            except AttributeError:
                try:
                    env.append(('Uname', sys.getwindowsversion()))
                except AttributeError:
                    env.append(('Uname', 'Unknown'))
        env.append(('Version', sys.version))
        env.append(('Byteorder', sys.byteorder))
        env.append(('Encoding', sys.getfilesystemencoding()))
        env.append(('Preferred encoding', locale.getpreferredencoding()))
        env.append(('Current dir', os.getcwd()))
        env.append(('Globals', os.environ))
        env.append(('Python path', sys.path))
        env.append(('Flags', sys.flags))
        return env

    def format_environment(self):
        """ Prints the gathered environmental data in key:value form. """
        return '\n'.join('%s:\t%s' % (key, pformat(value))
                for key, value in self._get_environment())

    @pyqtSlot(bool)
    def _details_toggled(self, toggled):
        if toggled:
            self.error_traceback.setPlainText(self._bug_dump)
            self.resize(800, 600)
        else:
            self.error_traceback.setPlainText(self._caption)
            self.resize(400, 300)

    def get_bug_dump(self):
        return self._bug_dump

    def prepare_error(self, caption, traceback):
        """ Displays the error widget showing caption. """
        self._caption = caption
        self._traceback = traceback
        self._bug_dump = '\n'.join([
                self._traceback, self.format_environment()])
        self.error_traceback.setPlainText(caption)

