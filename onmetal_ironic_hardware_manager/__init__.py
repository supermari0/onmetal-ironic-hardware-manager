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

import os

from ironic_python_agent import errors
from ironic_python_agent import hardware
from ironic_python_agent.openstack.common import log
from ironic_python_agent import utils

DDCLI = '/mnt/bin/ddcli'


LOG = log.getLogger()


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
                'reboot_requested': True,
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
        ]

    def decom_bios_settings(self, driver_info):
        LOG.info('Decom BIOS Settings called with %s' % driver_info)

    def customer_bios_settings(self, driver_info):
        LOG.info('NOOP: Customer BIOS Settings called with %s' % driver_info)

    def upgrade_bios(self, driver_info):
        LOG.info('Update BIOS called with %s' % driver_info)

    def update_warpdrive_firmware(self, driver_info):
        LOG.info('NOOP: Update Warpdrive called with %s' % driver_info)

    def update_intel_nic_firmware(self, driver_info):
        LOG.info('NOOP: Update Intel NIC called with %s' % driver_info)

    def _erase_lsi_warpdrive(self, block_device):
        device_name = os.path.basename(block_device.name)
        sys_block_path = '{0}/block/{1}'.format(self.sys_path, device_name)
        model_path = '{0}/device/model'.format(sys_block_path)

        try:
            with open(model_path) as model_file:
                model_str = model_file.read().strip()
                if not model_str == 'NWD-BLP4-1600':
                    return False
        except Exception:
            return False

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

        lines = utils.execute(DDCLI, '-listall')[0].split('\n')

        matching_lines = [line for line in lines if 'NWD-BLP4-1600' in line and
                          pci_address in line]

        if len(matching_lines) == 0:
            raise errors.BlockDeviceEraseError(('Unable to locate an LSI card '
                'with a PCI Address matching {0} for block device {1}').format(
                    pci_address, block_device.name))

        if len(matching_lines) > 1:
            raise errors.BlockDeviceEraseError(('Found multiple LSI cards '
                'with a PCI Address matching {0} for block device {1}').format(
                    pci_address, block_device.name))

        line = matching_lines[0]
        controller_id = line.split()[0]
        result = utils.execute(DDCLI, '-c', controller_id, '-format', '-s')
        if 'WarpDrive format successfully completed.' not in result[0]:
            raise errors.BlockDeviceEraseError(('Erasing LSI card failed: '
                '{0}').format(result[0]))

        return True
