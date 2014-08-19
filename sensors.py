#!/usr/bin/python3
# coding: utf-8
#
# A simple indicator applet displaying cpu and memory information
#
# Author: Alex Eftimie <alex@eftimie.ro>
# Fork Author: fossfreedom <foss.freedom@gmail.com>
# Original Homepage: http://launchpad.net/indicator-sysmonitor
# Fork Homepage: https://github.com/fossfreedom/indicator-sysmonitor
# License: GPL v3
#

import time
from threading import Thread
import subprocess
import copy
import re
from gettext import gettext as _

import psutil as ps


B_UNITS = ['', 'KB', 'MB', 'GB', 'TB']
HELP_MSG = """<span underline="single" size="x-large">{title}</span>

{introduction}

{basic}
• cpu: {cpu_desc}
• mem: {mem_desc}
• bat<i>%d</i>: {bat_desc}
• net: {net_desc}

{compose}
• fs//<i>mount-point</i> : {fs_desc}

<big>{example}</big>
CPU {{cpu}} | MEM {{mem}} | root {{fs///}}
""".format(
    title=_("Help Page"),
    introduction=_("The sensors are the names of the devices you want to \
    retrieve information from. They must be placed between brackets."),
    basic=_("The basics are:"),
    cpu_desc=_("It shows the average of CPU usage."),
    mem_desc=_("It shows the physical memory in use."),
    bat_desc=_("It shows the available battery which id is %d."),
    net_desc=_("It shows the amount of data you are downloading and uploading \
    through your network."),
    compose=_("Also there are the following sensors that are composed with \
    two parts divided by two slashes."),
    fs_desc=_("Show available space in the file system."),
    example=_("Example:"))

supported_sensors = re.compile("\A(mem|swap|cpu\d*|net|bat\d*|fs//.+)\Z")

settings = {
    'custom_text': 'cpu: {cpu} mem: {mem}',
    'interval': 2,
    'on_startup': False,
    'sensors': {
        # 'name' => (desc, cmd)
        'cpu\d*': (_('Average CPU usage'), True),
        'mem': (_('Physical memory in use.'), True),
        'net': (_('Network activity.'), True),
        'bat\d*': (_('Battery capacity.'), True),
        'fs//.+': (_('Available space in file system.'), True),
        "swap": (_("Average swap usage"), True)
    }
}


def bytes_to_human(bytes_):
    unit = 0
    while bytes_ > 1024:
        unit += 1
        bytes_ /= 1024

    return '{}{}'.format(int(bytes_), B_UNITS[unit])


class ISMError(Exception):
    """General exception."""

    def __init__(self, msg):
        Exception.__init__(self, msg)


class Sensor(object):
    """Singleton"""
    _instance = None
    bat = re.compile("\Abat\d*\Z")
    cpus = re.compile("\Acpu\d+\Z")

    def __init__(self):
        """It must not be called. Use Sensor.get_instance()
        to retrieve an instance of this class."""
        if Sensor._instance is not None:
            raise Exception("Sensor class can not be started twice.")
        else:
            Sensor._instance = self
        self.update_regex()

    @staticmethod
    def update_regex(names=None):
        if names is None:
            names = list(settings["sensors"].keys())

        reg = '|'.join(names)
        reg = "\A({})\Z".format(reg)
        global supported_sensors
        supported_sensors = re.compile("{}".format(reg))

    @classmethod
    def get_instance(cls):
        """Returns the unique instance of Sensor."""
        if Sensor._instance is None:
            Sensor._instance = Sensor()

        return Sensor._instance

    @staticmethod
    def exists(name):
        """Checks if the sensor name exists"""
        print(name)
        print(bool(supported_sensors.match(name)))
        return bool(supported_sensors.match(name))

    @staticmethod
    def check(sensor):
        if sensor.startswith("fs//"):
            path = sensor.split("//")[1]
            if not os.path.exists(path):
                raise ISMError(_("Path: {} doesn't exists.").format(path))

        elif Sensor.cpus.match(sensor):
            nber = int(sensor[3:])
            if nber >= ps.NUM_CPUS:
                raise ISMError(_("Invalid number of CPUs."))

        elif Sensor.bat.match(sensor):
            bat_id = int(sensor[3:]) if len(sensor) > 3 else 0
            if not os.path.exists("/sys/class/power_supply/BAT{}".format(bat_id)):
                raise ISMError(_("Invalid number returned for the Battery sensor."))

    def add(self, name, desc, cmd):
        """Adds a custom sensors."""
        if Sensor.exists(name):
            raise ISMError(_("Sensor name already in use."))

        settings["sensors"][name] = (desc, cmd)
        self.update_regex()

    def delete(self, name):
        """Deletes a custom sensors."""
        sensors = settings['sensors']
        names = list(sensors.keys())
        if name not in names:
            raise ISMError(_("Sensor is not defined."))

        _desc, default = sensors[name]
        if default is True:
            raise ISMError(_("Can not delete default sensors."))

        del sensors[name]
        self.update_regex()

    def edit(self, name, newname, desc, cmd):
        """Edits a custom sensors."""
        try:
            sensors = settings['sensors']
            _desc, default = sensors[name]

        except KeyError:
            raise ISMError(_("Sensor does not exists."))

        if default is True:
            raise ISMError(_("Can not edit default sensors."))
        if newname != name:
            if newname in list(sensors.keys()):
                raise ISMError(_("Sensor name already in use."))

        sensors[newname] = (desc, cmd)
        del sensors[name]
        settings["custom_text"] = settings["custom_text"].replace(
            name, newname)
        self.update_regex()


class StatusFetcher(Thread):
    """It recollects the info about the sensors."""
    digit_regex = re.compile(r'''\d+''')

    def __init__(self, parent):
        Thread.__init__(self)
        self._parent = parent
        self.last = ps.cpu_times()
        self._last_net_usage = [0, 0]  # (up, down)

    def _fetch_cpu(self, percpu=False):
        if percpu:
            return ps.cpu_percent(interval=0, percpu=True)

        last = self.last
        current = ps.cpu_times()

        total_time_passed = sum(
            [v - last.__dict__[k]
             if not isinstance(v, list)
             else 0
             for k, v in current.__dict__.items()])

        sys_time = current.system - last.system
        usr_time = current.user - last.user

        self.last = current

        if total_time_passed > 0:
            sys_percent = 100 * sys_time / total_time_passed
            usr_percent = 100 * usr_time / total_time_passed
            return sys_percent + usr_percent
        else:
            return 0

    def _fetch_swap(self):
        """Return the swap usage in percent"""
        usage = 0
        total = 0
        try:
            with open("/proc/swaps") as swaps:
                swaps.readline()
                for line in swaps.readlines():
                    dummy, dummy, total_, usage_, dummy = line.split()
                    total += int(total_)
                    usage += int(usage_)

                if total == 0:
                    return 0
                else:
                    return usage * 100 / total

        except IOError:
            return "N/A"

    def _fetch_mem(self):
        """It gets the total memory info and return the used in percent."""
        with open('/proc/meminfo') as meminfo:
            total = StatusFetcher.digit_regex.findall(meminfo.readline()).pop()
            free = StatusFetcher.digit_regex.findall(meminfo.readline()).pop()
            meminfo.readline()
            cached = StatusFetcher.digit_regex.findall(
                meminfo.readline()).pop()
            free = int(free) + int(cached)
            return 100 - 100 * free / float(total)

    def _fetch_bat(self, batid):
        """Fetch the the amount of remaining battery"""
        capacity = 0
        try:
            with open("/sys/class/power_supply/BAT{}/capacity".format(batid)) as state:
                while True:
                    capacity = int(state.readline())
                    break

        except IOError:
            return "N/A"

        return capacity

    def _fetch_net(self):
        """It returns the bytes sent and received in bytes/second"""
        current = [0, 0]
        for _, iostat in list(ps.network_io_counters(pernic=True).items()):
            current[0] += iostat.bytes_recv
            current[1] += iostat.bytes_sent
        dummy = copy.deepcopy(current)

        current[0] -= self._last_net_usage[0]
        current[1] -= self._last_net_usage[1]
        self._last_net_usage = dummy
        current[0] /= settings['interval']
        current[1] /= settings['interval']
        return '↓{}/s ↑{}/s'.format(bytes_to_human(current[0]),
                                    bytes_to_human(current[1]))

    def fetch(self):
        """Return a dict whose element are the sensors
        and their values"""
        res = {}
        cpus = None
        from preferences import Preferences

        for sensor in Preferences.sensors_regex.findall(
                settings["custom_text"]):
            sensor = sensor[1:-1]
            if sensor == 'cpu':
                res['cpu'] = "{:02.0f}%".format(self._fetch_cpu())
            elif Sensor.cpus.match(sensor):
                if cpus is None:
                    cpus = self._fetch_cpu(percpu=True)
                res[sensor] = "{:02.0f}%".format(cpus[int(sensor[3:])])

            elif sensor == 'mem':
                res['mem'] = '{:02.0f}%'.format(self._fetch_mem())
            elif sensor == 'net':
                res['net'] = self._fetch_net()

            elif Sensor.bat.match(sensor):
                bat_id = int(sensor[3:]) if len(sensor) > 3 else 0
                res[sensor] = '{:02.0f}%'.format(self._fetch_bat(bat_id))

            elif sensor.startswith('fs//'):
                parts = sensor.split('//')
                res[sensor] = self._fetch_fs(parts[1])

            elif sensor == "swap":
                res[sensor] = '{:02.0f}%'.format(self._fetch_swap())

            else:  # custom sensor
                res[sensor] = self._exec(settings["sensors"][sensor][1])

        return res

    def _exec(self, command):
        """Execute a custom command."""
        try:
            output = subprocess.Popen(command, stdout=subprocess.PIPE,
                                      shell=True).communicate()[0].strip()
        except:
            output = _("Error")
            logging.error(_("Error running: {}").format(command))

        return output.decode('utf-8') if output else _("(no output)")

    def _fetch_fs(self, mount_point):
        """It returns the amount of bytes available in the fs in
        a human-readble format."""
        if not os.access(mount_point, os.F_OK):
            return None

        stat = os.statvfs(mount_point)
        bytes_ = stat.f_bavail * stat.f_frsize

        for unit in B_UNITS:
            if bytes_ < 1024:
                return "{} {}".format(bytes_, unit)
            bytes_ /= 1024

    def run(self):
        """It is the main loop."""
        while self._parent.alive.isSet():
            data = self.fetch()
            self._parent.update(data)
            time.sleep(settings["interval"])
