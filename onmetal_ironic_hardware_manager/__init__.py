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
from ironic_python_agent import utils


class OnMetalHardwareManager(hardware.GenericHardwareManager):
    def evaluate_hardware_support(cls):
        return hardware.HardwareSupport.SERVICE_PROVIDER

    def erase_block_device(self, block_device):
        if self._erase_lsi_warpdrive(block_device):
            return

        super(OnMetalHardwareManager, self).erase_block_device(block_device)

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

        lines = utils.execute('ddcli', '-listall')[0].split('\n')

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
        result = utils.execute('ddcli', '-c', controller_id, '-s')[0]
        if 'WarpDrive format successfully completed.' not in result:
            raise errors.BlockDeviceEraseError(('Erasing LSI card failed: '
                '{0}').format(result))

        return True
