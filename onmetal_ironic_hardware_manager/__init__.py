# Copyright 2014 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import os
import re

from ironic_python_agent import errors
from ironic_python_agent import hardware
from ironic_python_agent import netutils
from ironic_python_agent import utils


# Directory that all BIOS utilities are located in
BIOS_DIR = '/mnt/bios/quanta_A14'
LSI_MODEL = 'NWD-BLP4-1600'
# Directory that all the LSI utilities/firmware are located in
LSI_FIRMWARE_VERSION = '11.00.00.00'
LSI_WARPDRIVE_DIR = os.path.join('/mnt/LSI', LSI_FIRMWARE_VERSION)
DDCLI = os.path.join(LSI_WARPDRIVE_DIR, 'ddcli')

LLDP_PORT_TYPE = 2
LLDP_CHASSIS_TYPE = 5

LOG = logging.getLogger(__name__)


class OnMetalHardwareManager(hardware.GenericHardwareManager):
    HARDWARE_MANAGER_VERSION = "1"

    def evaluate_hardware_support(cls):
        return hardware.HardwareSupport.SERVICE_PROVIDER

    def erase_block_device(self, block_device):
        if self._erase_lsi_warpdrive(block_device):
            return

        super(OnMetalHardwareManager, self).erase_block_device(block_device)

    def get_decommission_steps(self):
        """Get a list of decommission steps with priority

        Returns a list of dicts of the following form:
        {'function': the HardwareManager function to call.
         'priority': the order to call, starting at 1. If two steps share
                    the same priority, their order is undefined.
         'reboot_requested': Whether the agent should request Ironic reboots
                             it after the operation completes.
         'state': The state the machine will be in when the operation
                  completes. This will match the decommission_target_state
                  saved in the Ironic node.
        :return: a default list of decommission steps, as a list of
        dictionaries
        """
        return [
            {
                'state': 'upgrade_bios',
                'function': 'upgrade_bios',
                'priority': 10,
                'reboot_requested': True,
            },
            {
                'state': 'decom_bios_settings',
                'function': 'decom_bios_settings',
                'priority': 20,
                'reboot_requested': True,
            },
            {
                'state': 'update_warpdrive_firmware',
                'function': 'update_warpdrive_firmware',
                'priority': 30,
                'reboot_requested': False,
            },
            {
                'state': 'update_intel_nic_firmware',
                'function': 'update_intel_nic_firmware',
                'priority': 31,
                'reboot_requested': True,
            },
            {
                'state': 'erase_devices',
                'function': 'erase_devices',
                'priority': 40,
                'reboot_requested': False,
            },
            {
                'state': 'customer_bios_settings',
                'function': 'customer_bios_settings',
                'priority': 50,
                'reboot_requested': True,
            },
            {
                'state': 'verify_properties',
                'function': 'verify_properties',
                'priority': None,
                'reboot_requested': False
            },
            {
                'state': 'verify_ports',
                'function': 'verify_ports',
                'priority': 61,
                # Reboot into fresh agent before we allowing deploys
                'reboot_requested': True
            }
        ]

    def decom_bios_settings(self, node, ports):
        driver_info = node.get('driver_info', {})
        LOG.info('Decom BIOS Settings called with %s' % driver_info)
        cmd = os.path.join(BIOS_DIR, 'write_bios_settings_decom.sh')
        utils.execute(cmd, check_exit_code=[0])
        return True

    def customer_bios_settings(self, node, ports):
        driver_info = node.get('driver_info', {})
        LOG.info('Customer BIOS Settings called with %s' % driver_info)
        cmd = os.path.join(BIOS_DIR, 'write_bios_settings_customer.sh')
        utils.execute(cmd, check_exit_code=[0])
        return True

    def upgrade_bios(self, node, ports):
        driver_info = node.get('driver_info', {})
        LOG.info('Update BIOS called with %s' % driver_info)
        cmd = os.path.join(BIOS_DIR, 'flash_bios.sh')
        utils.execute(cmd, check_exit_code=[0])
        return True

    def update_warpdrive_firmware(self, node, ports):
        driver_info = node.get('driver_info', {})
        LOG.info('Update Warpdrive called with %s' % driver_info)
        devices = self._list_lsi_devices()
        for device in devices:
            # Don't reflash the same firmware
            if device['version'] != LSI_FIRMWARE_VERSION:
                filename = '%(model)s_%(version)s.bin' % {
                    'model': device['model'],
                    'version': LSI_FIRMWARE_VERSION
                }
                firmware_path = os.path.join(LSI_WARPDRIVE_DIR,
                                             filename)
                cmd = [DDCLI, '-c', device['id'], '-updatepkg', firmware_path]
                utils.execute(*cmd, check_exit_code=[0])
            else:
                LOG.info('Device %(id)s already version %(version)s, '
                         'not upgrading.' % {
                             'id': device['id'],
                             'version': device['version']
                         })

    def update_intel_nic_firmware(self, node, ports):
        LOG.info('NOOP: Update Intel NIC called with %s' %
                 node.get('driver_info'))

    def _list_lsi_devices(self):
        lines = utils.execute(DDCLI, '-listall')[0].split('\n')
        matching_devices = [line.split() for line in lines if LSI_MODEL
                            in line]
        devices = []
        for line in matching_devices:
            devices.append({
                'id': line[0].strip(),
                'model': line[1].strip(),
                'version': line[2].strip(),
                # Strip the last :00 to match the /sys/devices filename
                'pci_address': line[3].strip()[:-3]
            })
        return devices

    def _erase_lsi_warpdrive(self, block_device):
        if block_device.model != LSI_MODEL:
            return False
        device_name = os.path.basename(block_device.name)
        sys_block_path = '{0}/block/{1}'.format(self.sys_path, device_name)

        # NOTE(russell_h): Trying to map a block device name to an LSI card
        # gets a little weird. It seems like if we follow the /sys/block/<name>
        # symlink, we'll find something that looks like:
        #
        # /sys/devices/pci0000:00/0000:00:02.0/0000:02:00.0/host3/target3:1:0
        #     /3:1:0:0/block/sdb
        #
        # This seems to correspond to the card that ddcli reports has PCI
        # address 00:02:00:00
        real_path = os.path.realpath(sys_block_path)

        # pull out a segment such as 0000:02:00.0 and trim it to 00:02:00
        pci_address = real_path.split('/')[5][2:-2]

        devices = self._list_lsi_devices()

        matching_devices = [device for device in devices if
                            device['pci_address'] == pci_address]

        if len(matching_devices) == 0:
            raise errors.BlockDeviceEraseError(('Unable to locate an LSI card '
                'with a PCI Address matching {0} for block device {1}').format(
                    pci_address, block_device.name))

        if len(matching_devices) > 1:
            raise errors.BlockDeviceEraseError(('Found multiple LSI cards '
                'with a PCI Address matching {0} for block device {1}').format(
                    pci_address, block_device.name))

        device = matching_devices[0]
        result = utils.execute(DDCLI, '-c', device['id'], '-format', '-op',
                '-level', 'cap', '-s')
        if 'WarpDrive format successfully completed.' not in result[0]:
            raise errors.BlockDeviceEraseError(('Erasing LSI card failed: '
                '{0}').format(result[0]))

        return True

    def verify_ports(self, node, ports):
        """Given Port dicts, verify they match LLDP information

        :param node: a dict representation of a Node object
        :param ports: a dict representation of Ports connected to the node
        :raises VerificationException: if any of the steps determine the node
                does not match the given data
        :raises VerificationStepDoesNotExist: if a given step isn't a function
                of the hardware manager
        """
        interface_names = [x.name for x in self.list_network_interfaces()]
        lldp_info = netutils.get_lldp_info(interface_names)

        # Both should be a set of tuples: (chassis, port)
        lldp_ports = set()

        for lldp in lldp_info.values():
            lldp_ports.add(self._get_port_from_lldp(lldp))
        LOG.info('LLDP ports: %s', lldp_ports)
        node_ports = self._get_node_ports(node, ports)
        LOG.info('Node ports: %s', node_ports)
        # TODO(JoshNang) add check that ports, chassis *and* interface match
        # when port/chassis are stored on Port objects

        # Compare the ports
        if node_ports != lldp_ports:
            LOG.error('Ports did not match, LLDP: %(lldp)s, Node: %(node)s',
                      {'lldp': lldp_ports, 'node': node_ports})
            raise errors.VerificationFailed(
                'Detected port mismatches. LLDP detected_ports: %(lldp)s, '
                'Node ports: %(node)s.' %
                {'lldp': lldp_ports, 'node': node_ports})

        # Return the LLDP info
        LOG.debug('Ports match, returning LLDP info: %s', lldp_info)
        # Ensure the return value is properly encode or JSON throws errors
        return unicode(lldp_info)

    def _get_port_from_lldp(self, lldp_info):
        """Return a set of tuples (chassis, port) from the given LLDP info

        :param lldp_info: the return from netutils.get_lldp_info()
        :return: a Set of tuples (chassis, port)
        """

        tlv_port = self._get_tlv(LLDP_PORT_TYPE, lldp_info)
        tlv_chassis = self._get_tlv(LLDP_CHASSIS_TYPE, lldp_info)

        if len(tlv_port) != 1 or len(tlv_chassis) != 1:
            raise errors.VerificationError(
                'Malformed LLDP info. Received port: %(port)s, '
                'chassis: %(chassis)s' %
                {'port': tlv_port, 'chassis': tlv_chassis})

        port_number = re.search(r'\d{1,2}/\d{1,2}', tlv_port[0])
        lldp_port = 'eth' + port_number.group()
        return tlv_chassis[0].lower(), lldp_port.lower()

    def _get_node_ports(self, node, ports):
        """Find the chassis and ports the node is attached to

        Return a set of tuples (chassis, port). Supports pulling them
        from node['extra'], with support for pull chassis/port/interface from
        port['extra'] in the future.

        :param node: a dict representation of a Node object
        :param ports: a dict representation of Ports connected to the node
        :return: a Set of tuples (chassis, port)
        """
        ports = set()
        LOG.info('Matching against node ports: %s', node.get('extra'))
        for key, val in node.get('extra', {}).items():
            match = re.search(r'hardware/interfaces/(?P<id>\d+)/'
                              r'switch_chassis_id', key)
            if match:
                index = match.group('id')
                port_key = r'hardware/interfaces/%s/switch_port_id' % index
                try:
                    ports.add((val.lower(), node['extra'][port_key].lower()))
                except KeyError:
                    raise errors.VerificationError(
                        'Node has malformed extra data, could not find chassis'
                        ' and port: %s' % node['extra'])
        return ports

    def _get_tlv(self, tlv_type, lldp_info):
        """Return all LLDP values that match a TLV type (an int) as a list."""
        # Use a list because TLV type 127 may be be used multiple times in LLDP
        values = []
        for tlv in lldp_info:
            if len(tlv) != 2:
                raise errors.VerificationError('Malformed LLDP info %s'
                                               % lldp_info)
            if tlv[0] == tlv_type:
                values.append(tlv[1])
        return values
