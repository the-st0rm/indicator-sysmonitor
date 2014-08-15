import shutil
import re
from gi.repository import Gtk
from sensors import Sensor
from sensors import settings
from sensors import ISMError
import os
from gettext import gettext as _

VERSION = '0.5.0~stable'

def raise_dialog(parent, flags, type_, buttons, msg, title):
    """It raise a dialog. It a blocking function."""
    dialog = Gtk.MessageDialog(
        parent, flags, type_, buttons, msg)
    dialog.set_title(title)
    dialog.run()
    dialog.destroy()

class SensorsListModel(object):
    """A TreeView showing the available sensors. It allows to
    add/edit/delete custom sensors."""

    def __init__(self, parent):
        self.ind_parent = parent
        self._list_store = Gtk.ListStore(str, str)
        self._tree_view = Gtk.TreeView(self._list_store)

        sensors = settings['sensors']
        for name in list(sensors.keys()):
            self._list_store.append([name, sensors[name][0]])

    def get_view(self):
        """It's called from Preference. It creates the view and returns it"""
        vbox = Gtk.VBox(False, 3)
        # create columns
        renderer = Gtk.CellRendererText()
        renderer.set_property('editable', False)
        column = Gtk.TreeViewColumn(_('Sensor'), renderer, text=0)
        self._tree_view.append_column(column)

        renderer = Gtk.CellRendererText()
        renderer.set_property('editable', False)
        column = Gtk.TreeViewColumn(_('Description'), renderer, text=1)
        self._tree_view.append_column(column)

        self._tree_view.expand_all()
        sw = Gtk.ScrolledWindow()
        sw.add_with_viewport(self._tree_view)
        vbox.pack_start(sw, True, True, 0)

        # add buttons
        hbox = Gtk.HBox()
        new_button = Gtk.Button.new_from_stock(Gtk.STOCK_NEW)
        new_button.connect('clicked', self._on_edit_sensor)
        hbox.pack_start(new_button, False, False, 0)

        edit_button = Gtk.Button.new_from_stock(Gtk.STOCK_EDIT)
        edit_button.connect('clicked', self._on_edit_sensor, False)
        hbox.pack_start(edit_button, False, False, 1)

        del_button = Gtk.Button.new_from_stock(Gtk.STOCK_DELETE)
        del_button.connect('clicked', self._on_del_sensor)
        hbox.pack_start(del_button, False, False, 2)

        add_button = Gtk.Button.new_from_stock(Gtk.STOCK_ADD)
        add_button.connect('clicked', self._on_add_sensor)
        hbox.pack_end(add_button, False, False, 3)
        vbox.pack_end(hbox, False, False, 1)

        frame = Gtk.Frame.new(_('Sensors'))
        frame.add(vbox)
        return frame

    def _get_selected_row(self):
        """Returns an iter for the selected rows in the view or None."""
        model, pathlist = self._tree_view.get_selection().get_selected_rows()
        if len(pathlist):
            path = pathlist.pop()
            return model.get_iter(path)
        return None

    def _on_add_sensor(self, evnt=None, data=None):
        tree_iter = self._get_selected_row()
        if tree_iter is None:
            return

        sensor = self._list_store.get_value(tree_iter, 0)
        self.ind_parent.custom_entry.insert_text(
            "{{{}}}".format(sensor), -1)

    def _on_edit_sensor(self, evnt=None, blank=True):
        """Raises a dialog with a form to add/edit a sensor"""
        name = desc = cmd = ""
        tree_iter = None
        if not blank:
            # edit, so get the info from the selected row
            tree_iter = self._get_selected_row()
            if tree_iter is None:
                return

            name = self._list_store.get_value(tree_iter, 0)
            desc = self._list_store.get_value(tree_iter, 1)
            cmd = settings["sensors"][name][1]

            if cmd is True:  # default sensor
                raise_dialog(
                    self.ind_parent,
                    Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                    Gtk.MessageType.ERROR, Gtk.ButtonsType.OK,
                    _("Can not edit the default sensors."), _("Error"))
                return

        dialog = Gtk.Dialog(_("Edit Sensor"), self.ind_parent,
                            Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                            (Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT,
                             Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT))
        vbox = dialog.get_content_area()

        hbox = Gtk.HBox()
        label = Gtk.Label(_("Sensor"))
        sensor_entry = Gtk.Entry()
        sensor_entry.set_text(name)
        hbox.pack_start(label, False, False, 0)
        hbox.pack_end(sensor_entry, False, False, 1)
        vbox.pack_start(hbox, False, False, 0)

        hbox = Gtk.HBox()
        label = Gtk.Label(_("Description"))
        desc_entry = Gtk.Entry()
        desc_entry.set_text(desc)
        hbox.pack_start(label, False, False, 0)
        hbox.pack_end(desc_entry, False, False, 1)
        vbox.pack_start(hbox, False, False, 1)

        hbox = Gtk.HBox()
        label = Gtk.Label(_("Command"))
        cmd_entry = Gtk.Entry()

        cmd_entry.set_text(cmd)
        hbox.pack_start(label, False, False, 0)
        hbox.pack_end(cmd_entry, False, False, 1)
        vbox.pack_end(hbox, False, False, 2)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.ACCEPT:
            try:
                newname, desc, cmd = str(sensor_entry.get_text()), \
                                     str(desc_entry.get_text()), str(cmd_entry.get_text())

                if blank:
                    Sensor.get_instance().add(newname, desc, cmd)
                else:
                    Sensor.get_instance().edit(name, newname, desc, cmd)
                    self._list_store.remove(tree_iter)

                self._list_store.append([newname, desc])
                ctext = self.ind_parent.custom_entry.get_text()

                # issue 3: why we are doing a character replacement when clicking
                #new - who knows ... lets just comment this out
                #self.ind_parent.custom_entry.set_text(
                #    ctext.replace(name, newname))

            except ISMError as ex:
                raise_dialog(
                    self.ind_parent,
                    Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                    Gtk.MessageType.ERROR, Gtk.ButtonsType.OK,
                    ex, _("Error"))

        dialog.destroy()

    def _on_del_sensor(self, evnt=None, data=None):
        """Remove a custom sensor."""
        tree_iter = self._get_selected_row()
        if tree_iter is None:
            return

        name = self._list_store.get_value(tree_iter, 0)
        try:
            Sensor.get_instance().delete(name)
            self._list_store.remove(tree_iter)
            ctext = self.ind_parent.custom_entry.get_text()
            self.ind_parent.custom_entry.set_text(
                ctext.replace("{{{}}}".format(name), ""))

        except ISMError as ex:
            raise_dialog(
                self.ind_parent,
                Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                Gtk.MessageType.ERROR, Gtk.ButtonsType.OK,
                ex, _("Error"))


class Preferences(Gtk.Dialog):
    """It define the the Preferences Dialog and its operations."""
    AUTOSTART_DIR = '{}/.config/autostart' \
        .format(os.getenv("HOME"))
    AUTOSTART_PATH = '{}/.config/autostart/indicator-sysmonitor.desktop' \
        .format(os.getenv("HOME"))
    DESKTOP_PATH = '/usr/share/applications/indicator-sysmonitor.desktop'
    sensors_regex = re.compile("{.+?}")

    def __init__(self, parent):
        """It creates the widget of the dialogs"""
        Gtk.Dialog.__init__(self)
        self.ind_parent = parent
        self.custom_entry = None
        self.interval_entry = None
        self._create_content()
        self.set_data()
        self.show_all()

    def _create_content(self):
        """It creates the content for this dialog."""
        self.connect('delete-event', self.on_cancel)
        self.set_title(_('Preferences'))
        self.resize(400, 350)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        notebook = Gtk.Notebook()
        notebook.set_border_width(4)

        # General page of the notebook {{{
        vbox = Gtk.VBox(spacing=3)
        hbox = Gtk.HBox()

        hbox.set_border_width(4)
        label = Gtk.Label(_('Run on startup:'))
        label.set_alignment(0, 0.5)
        hbox.pack_start(label, False, False, 0)
        self.autostart_check = Gtk.CheckButton()
        self.autostart_check.set_active(self.get_autostart())
        hbox.pack_end(self.autostart_check, False, False, 1)
        vbox.pack_start(hbox, False, False, 0)

        hbox = Gtk.HBox()
        label = Gtk.Label(
            _('This is indicator-sysmonitor version: {}').format(VERSION))
        label.set_alignment(0.5, 0.5)
        hbox.pack_start(label, False, False, 0)
        vbox.pack_end(hbox, False, False, 1)
        notebook.append_page(vbox, Gtk.Label(_('General')))
        # }}}

        # Advanced page in notebook {{{
        vbox = Gtk.VBox()  # main box
        label = Gtk.Label(_('Customize output:'))
        label.set_alignment(0, 0)
        vbox.pack_start(label, False, False, 0)
        self.custom_entry = Gtk.Entry()
        vbox.pack_start(self.custom_entry, False, False, 1)

        hbox = Gtk.HBox()
        label = Gtk.Label(_('Update interval:'))
        label.set_alignment(0, 0)
        hbox.pack_start(label, False, False, 0)
        self.interval_entry = Gtk.Entry(max_length=4)
        self.interval_entry.set_width_chars(5)

        hbox.pack_end(self.interval_entry, False, False, 1)
        vbox.pack_start(hbox, False, False, 2)

        sensors_list = SensorsListModel(self)
        vbox.pack_start(sensors_list.get_view(), True, True, 3)
        notebook.append_page(vbox, Gtk.Label(_('Advanced')))
        # }}}

        # footer {{{
        vbox = self.get_content_area()
        vbox.pack_start(notebook, True, True, 4)
        buttons = Gtk.HButtonBox()
        buttons.set_layout(Gtk.ButtonBoxStyle.EDGE)
        test = Gtk.Button(_('Test'))
        test.connect('clicked', self.on_test)
        buttons.pack_start(test, False, False, 0)
        # TODO: add an info message on hover

        cancel = Gtk.Button(stock=Gtk.STOCK_CANCEL)
        cancel.connect('clicked', self.on_cancel)
        buttons.pack_end(cancel, False, False, 1)

        close = Gtk.Button(stock=Gtk.STOCK_SAVE)
        close.connect('clicked', self.on_save)
        buttons.pack_end(close, False, False, 2)
        vbox.pack_end(buttons, False, False, 5)
        # }}}

    def on_test(self, evnt=None, data=None):
        """The action of the test button."""
        try:
            self.update_parent()
        except Exception as ex:
            error_dialog = Gtk.MessageDialog(
                None, Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.ERROR,
                Gtk.ButtonsType.CLOSE, ex)
            error_dialog.set_title("Error")
            error_dialog.run()
            error_dialog.destroy()
            return False

    def on_save(self, evnt=None, data=None):
        """The action of the save button."""
        try:
            self.update_parent()
        except Exception as ex:
            error_dialog = Gtk.MessageDialog(
                None, Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.ERROR,
                Gtk.ButtonsType.CLOSE, ex)
            error_dialog.set_title("Error")
            error_dialog.run()
            error_dialog.destroy()
            return False

        self.ind_parent.save_settings()
        self.update_autostart()
        self.destroy()

    def on_cancel(self, evnt=None, data=None):
        """The action of the cancel button."""
        self.ind_parent.load_settings()
        self.destroy()

    def update_parent(self, evnt=None, data=None):
        """It gets the config info from the widgets and sets them to the vars.
        It does NOT update the config file."""
        custom_text = self.custom_entry.get_text()

        # check if the sensors are supported
        sensors = Preferences.sensors_regex.findall(custom_text)
        for sensor in sensors:
            sensor = sensor[1:-1]
            if not Sensor.exists(sensor):
                raise ISMError(_("{{{}}} sensor not supported.").
                               format(sensor))
            # Check if the sensor is well-formed
            Sensor.check(sensor)

        try:
            interval = float(self.interval_entry.get_text())
            if interval <= 0:
                raise ISMError(_("Interval value is not valid."))

        except ValueError:
            raise ISMError(_("Interval value is not valid."))

        settings["custom_text"] = custom_text
        settings["interval"] = interval
        # TODO: on_startup
        self.ind_parent.update_indicator_guide()

    def set_data(self):
        """It sets the widgets with the config data."""
        self.custom_entry.set_text(settings["custom_text"])
        self.interval_entry.set_text(str(settings["interval"]))

    def update_autostart(self):
        autostart = self.autostart_check.get_active()
        if not autostart:
            try:
                os.remove(Preferences.AUTOSTART_PATH)
            except:
                pass
        else:
            try:
                if not os.path.exists(Preferences.AUTOSTART_DIR):
                    os.makedirs(Preferences.AUTOSTART_DIR)

                shutil.copy(Preferences.DESKTOP_PATH,
                            Preferences.AUTOSTART_PATH)
            except Exception as ex:
                logging.exception(ex)

    def get_autostart(self):
        return os.path.exists(Preferences.AUTOSTART_PATH)
