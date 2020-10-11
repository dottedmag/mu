"""
A mode for working with Snek boards. https://keithp.com/snek

Copyright © 2019 Keith Packard

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import logging
from mu.modes.base import BaseMode
from mu.modes.api import SNEK_NET_APIS
#from mu.interface.panes import CHARTS
from PyQt5.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)


class ZeroconfListener:
    def __init__(self):
        self.services = {}

    def add_service(self, zc, type, name):
        info = zc.get_service_info(type, name)
        if len(info.addresses) > 0:
            address = "{}.{}.{}.{}".format(
                info.addresses[0][0],
                info.addresses[0][1],
                info.addresses[0][2],
                info.addresses[0][3],
            )
            self.services[name] = (address, info.port)

    def remove_service(self, zc, type, name):
        self.services.pop(name, None)


li = ZeroconfListener()


try:
    import zeroconf

    zc = zeroconf.Zeroconf()
    br = zeroconf.ServiceBrowser(zc, "_snek._tcp.local.", li)
except ImportError:
    pass


class SnekNetMode(BaseMode):
    """
    Represents the functionality required by the Snek network mode.
    """

    name = _("Snek Network")
    description = _("Write code for boards running Snek Network.")
    icon = "snek-net"
    save_timeout = 0  #: No auto-save on CP boards. Will restart.
    connected = True  #: is the board connected.
    force_interrupt = True  #: keyboard interrupt on serial connection.
    # Modules built into Snek which mustn't be used as file names
    # for source code.
    module_names = {"time", "random", "math"}
    builtins = (
        "abs_tol",
        "curses",
        "eeprom",
        "exit",
        "math",
        "neopixel",
        "off",
        "on",
        "onfor",
        "pulldown",
        "pullnone",
        "pullup",
        "random",
        "read",
        "rel_tol",
        "reset",
        "round",
        "setleft",
        "setpower",
        "setright",
        "stdscr",
        "stopall",
        "sys",
        "talkto",
        "temperature",
        "time",
    )

    def find_device(self, with_logging=True):
        for svc in li.services.values():
            logger.debug("Service {}".format(svc))
        for svc in li.services.values():
            return svc[0], svc[1]
        return (None, None)

    def stop(self):
        self.view.close_network_link()

    def actions(self):
        """
        Return an ordered list of actions provided by this module. An action
        is a name (also used to identify the icon) , description, and handler.
        """
        buttons = [
            {
                "name": "repl",
                "display_name": _("Connect"),
                "description": _("Connect to your device."),
                "handler": self.toggle_repl,
                "shortcut": "CTRL+Shift+U",
            },
            {
                "name": "flash",
                "display_name": _("Put"),
                "description": _("Put the current program to the device."),
                "handler": self.put,
                "shortcut": "CTRL+Shift+P",
            },
            {
                "name": "getflash",
                "display_name": _("Get"),
                "description": _("Get the current program from the device."),
                "handler": self.get,
                "shortcut": "CTRL+Shift+G",
            },
        ]
        return buttons

    def put(self):
        """
        Put the current program into the device memory.
        """
        logger.info("Downloading code to target device.")
        # Grab the Python script.
        tab = self.view.current_tab
        if tab is None:
            # There is no active text editor.
            message = _("Cannot run anything without any active editor tabs.")
            information = _(
                "Running transfers the content of the current tab"
                " onto the device. It seems like you don't have "
                " any tabs open."
            )
            self.view.show_message(message, information)
            return
        python_script = tab.text()
        if python_script[-1] != "\n":
            python_script += "\n"
        if not self.repl:
            self.toggle_repl(None)
        command = ("eeprom.write()\n" + python_script + "\x04" + "reset()\n",)
        print(repr(command))
        if self.repl:
            self.view.repl_pane.send_commands(command)

    def get_tab(self):
        for tab in self.view.widgets:
            if not tab.path:
                return tab
        return None

    def recv_text(self, text):
        target_tab = self.get_tab()
        if target_tab:
            target_tab.setText(text)
            target_tab.setModified(False)
        else:
            view = self.view
            editor = self.editor
            view.add_tab(None, text, editor.modes[editor.mode].api(), "\n")

    def get(self):
        """
        Get the current program from device memory.
        """
        target_tab = self.get_tab()
        if target_tab and target_tab.isModified():
            msg = "There is un-saved work, 'get' will cause you " "to lose it."
            window = target_tab.nativeParentWidget()
            if window.show_confirmation(msg) == QMessageBox.Cancel:
                return

        command = ("eeprom.show(1)\n",)
        if not self.repl:
            self.toggle_repl(None)
        if self.repl:
            self.view.repl_pane.text_recv = self
            self.view.repl_pane.send_commands(command)

    def api(self):
        """
        Return a list of API specifications to be used by auto-suggest and call
        tips.
        """
        return SNEK_NET_APIS

    def add_repl(self):
        """
        Detect a Snek Net based device and, if found, connect to
        the REPL and display it to the user.
        """
        device_addr, device_port = self.find_device()
        if device_addr:
            try:
                self.view.add_snek_net_repl(
                    device_addr, device_port, self.name, self.force_interrupt
                )
                logger.info("Started REPL on port: {}".format(device_port))
                self.repl = True
            except IOError as ex:
                print(ex)
                logger.error(ex)
                self.repl = False
                info = _(
                    "Click on the device's reset button, wait a few"
                    " seconds and then try again."
                )
                self.view.show_message(str(ex), info)
            except Exception as ex:
                print(ex)
                logger.error(ex)
        else:
            message = _("Could not find an attached device.")
            information = _(
                "Please make sure the device is plugged into this"
                " computer.\n\nIt must have a version of"
                " Snek flashed onto it"
                " before the REPL will work.\n\nFinally, press the"
                " device's reset button and wait a few seconds"
                " before trying again."
            )
            self.view.show_message(message, information)

    def remove_repl(self):
        """
        If there's an active REPL, disconnect and hide it.
        """
        self.view.remove_repl()
        self.repl = False

    def toggle_repl(self, event):
        """
        Toggles the REPL on and off.
        """
        if self.repl:
            self.remove_repl()
            logger.info("Toggle REPL off.")
        else:
            self.add_repl()
            logger.info("Toggle REPL on.")
