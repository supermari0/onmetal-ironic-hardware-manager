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

import mock
import os
import six

from ironic_python_agent import errors
from ironic_python_agent import hardware
from ironic_python_agent import utils
from oslotest import base as test_base

import onmetal_ironic_hardware_manager as onmetal_hardware_manager

if six.PY2:
    OPEN_FUNCTION_NAME = '__builtin__.open'
else:
    OPEN_FUNCTION_NAME = 'builtins.open'

DDCLI_LISTALL_OUT = (
    '\n'
    '*************************************************************************'
        '***\n'
    '   LSI Corporation WarpDrive Management Utility\n'
    '   Version 112.00.01.00 (2014.03.04)\n'
    '   Copyright (c) 2014 LSI Corporation. All Rights Reserved.\n'
    '*************************************************************************'
        '***\n'
    '\n'
    'ID    WarpDrive     Package Version    PCI Address\n'
    '--    ---------     ---------------    -----------\n'
    '1     NWD-BLP4-1600      11.00.00.00        00:02:00:00\n'
    '2     NWD-BLP4-1600      11.00.00.00        00:04:00:00\n'
    '\n'
    'LSI WarpDrive Management Utility: Execution completed successfully.\n'
)

DDCLI_FORMAT_OUT = (
    '\n'
    '*************************************************************************'
        '***\n'
    '   LSI Corporation WarpDrive Management Utility\n'
    '   Version 112.00.01.00 (2014.03.04)\n'
    '   Copyright (c) 2014 LSI Corporation. All Rights Reserved.\n'
    '*************************************************************************'
        '***\n'
    'LSI WarpDrive Management Utility: Preparing WarpDrive for format.\n'
    'LSI WarpDrive Management Utility: Please wait. Format of WarpDrive is in '
        'progress.....\n'
    'LSI WarpDrive Management Utility: WarpDrive format successfully '
        'completed.\n'
    '\n'
    'LSI WarpDrive Management Utility: Execution completed successfully.\n'
)


class TestOnMetalHardwareManager(test_base.BaseTestCase):
    def setUp(self):
        super(TestOnMetalHardwareManager, self).setUp()
        self.hardware = onmetal_hardware_manager.OnMetalHardwareManager()
        self.block_device = hardware.BlockDevice('/dev/sda', 'NWD-BLP4-1600',
                                                 1073741824, False)

        self.FAKE_DEVICES = [
            {
                'id': '1',
                'model': 'NWD-BLP4-1600',
                'pci_address': '00:02:00',
                'version': '11.00.00.00'
            },
            {
                'id': '2',
                'model': 'NWD-BLP4-1600',
                'pci_address': '00:04:00',
                'version': '11.00.00.00'
            }
        ]

    def _mock_file(self, mocked_open, contents):
        mocked_open.return_value.__enter__ = lambda s: s
        mocked_open.return_value.__exit__ = mock.Mock()
        read_mock = mocked_open.return_value.read
        read_mock.return_value = contents

    @mock.patch.object(utils, 'execute')
    def test__list_lsi_devices(self, mocked_execute):
        mocked_execute.side_effect = [
            (DDCLI_LISTALL_OUT, ''),
            (DDCLI_FORMAT_OUT, ''),
        ]
        devices = self.hardware._list_lsi_devices()
        self.assertEqual(self.FAKE_DEVICES, devices)

    @mock.patch.object(os.path, 'realpath')
    @mock.patch.object(utils, 'execute')
    def test_erase_block_device_lsi_success(self,
                                            mocked_execute,
                                            mocked_realpath):
        self.hardware._list_lsi_devices = mock.Mock()
        self.hardware._list_lsi_devices.return_value = self.FAKE_DEVICES

        # Mock the PCI address lookup
        mocked_realpath.return_value = ('/sys/devices/pci0000:00/0000:00:02.0'
            '/0000:02:00.0/host3/target3:1:0/3:1:0:0/block/sdb')

        mocked_execute.return_value = (DDCLI_FORMAT_OUT, '')

        self.hardware.erase_block_device(self.block_device)

        mocked_execute.assert_has_calls([
            mock.call(onmetal_hardware_manager.DDCLI,
            '-c', '1', '-format', '-op', '-level', 'cap', '-s')
        ])

    @mock.patch.object(os.path, 'realpath')
    @mock.patch.object(utils, 'execute')
    def test_erase_block_device_lsi_notfound(self,
                                             mocked_execute,
                                             mocked_realpath):
        self.hardware._list_lsi_devices = mock.Mock()
        self.hardware._list_lsi_devices.return_value = self.FAKE_DEVICES

        # The '0000:06:00.0' does not map to an address in the ddcli output
        mocked_realpath.return_value = ('/sys/devices/pci0000:00/0000:00:02.0'
            '/0000:06:00.0/host3/target3:1:0/3:1:0:0/block/sdb')

        self.assertRaises(errors.BlockDeviceEraseError,
                          self.hardware.erase_block_device,
                          self.block_device)

        mocked_execute.assert_has_calls([])

    @mock.patch.object(os.path, 'realpath')
    @mock.patch.object(utils, 'execute')
    def test_erase_block_device_lsi_multiple(self,
                                             mocked_execute,
                                             mocked_realpath):
        self.hardware._list_lsi_devices = mock.Mock()
        dupes = self.FAKE_DEVICES
        dupes[1]['pci_address'] = '00:02:00'
        self.hardware._list_lsi_devices.return_value = dupes

        mocked_realpath.return_value = ('/sys/devices/pci0000:00/0000:00:02.0'
            '/0000:02:00.0/host3/target3:1:0/3:1:0:0/block/sdb')

        self.assertRaises(errors.BlockDeviceEraseError,
                          self.hardware.erase_block_device,
                          self.block_device)

        mocked_execute.assert_has_calls([])

    @mock.patch.object(os.path, 'realpath')
    @mock.patch.object(utils, 'execute')
    def test_erase_block_device_lsi_error(self,
                                          mocked_execute,
                                          mocked_realpath):
        self.hardware._list_lsi_devices = mock.Mock()
        self.hardware._list_lsi_devices.return_value = self.FAKE_DEVICES

        mocked_realpath.return_value = ('/sys/devices/pci0000:00/0000:00:02.0'
            '/0000:02:00.0/host3/target3:1:0/3:1:0:0/block/sdb')

        # Presumably it doesn't print success on an error
        error_output = DDCLI_LISTALL_OUT.replace(
            'WarpDrive format successfully completed.',
            'Something went terribly, terribly wrong.')

        mocked_execute.return_value = (error_output, '')
        self.assertRaises(errors.BlockDeviceEraseError,
                          self.hardware.erase_block_device,
                          self.block_device)

        mocked_execute.assert_has_calls([
            mock.call(onmetal_hardware_manager.DDCLI,
                '-c', '1', '-format', '-op', '-level', 'cap', '-s'),
        ])

    @mock.patch('ironic_python_agent.hardware.GenericHardwareManager'
                '.erase_block_device')
    @mock.patch.object(utils, 'execute')
    def test_erase_block_device_defer_to_generic(self,
                                                 mocked_execute,
                                                 mocked_generic):

        self.block_device.model = 'NormalSSD'
        self.hardware.erase_block_device(self.block_device)
        mocked_execute.assert_has_calls([])
        mocked_generic.assert_has_calls([mock.call(self.block_device)])

    @mock.patch.object(utils, 'execute')
    def test_update_warpdrive_firmware(self, mocked_execute):
        onmetal_hardware_manager.LSI_FIRMWARE_VERSION = '10.0.0.0'
        onmetal_hardware_manager.LSI_WARPDRIVE_DIR = '/warpdrive/10.0.0.0'
        self.hardware._list_lsi_devices = mock.Mock()
        self.hardware._list_lsi_devices.return_value = self.FAKE_DEVICES
        self.hardware.update_warpdrive_firmware({})
        mocked_execute.assert_has_calls([
            mock.call(
                onmetal_hardware_manager.DDCLI, '-c', '1', '-updatepkg',
                '/warpdrive/10.0.0.0/NWD-BLP4-1600_10.0.0.0.bin',
                check_exit_code=[0]),
            mock.call(
                onmetal_hardware_manager.DDCLI, '-c', '2', '-updatepkg',
                '/warpdrive/10.0.0.0/NWD-BLP4-1600_10.0.0.0.bin',
                check_exit_code=[0])
        ])

    @mock.patch.object(utils, 'execute')
    def test_update_warpdrive_firmware_same_version(self, mocked_execute):
        onmetal_hardware_manager.LSI_FIRMWARE_VERSION = '12.0.0.0'
        self.hardware._list_lsi_devices = mock.Mock()
        self.hardware._list_lsi_devices.return_value = self.FAKE_DEVICES
        self.hardware.update_warpdrive_firmware({})
        mocked_execute.assert_has_calls([])


class TestOnMetalVerifyPorts(test_base.BaseTestCase):
    def setUp(self):
        super(TestOnMetalVerifyPorts, self).setUp()
        self.hardware = onmetal_hardware_manager.OnMetalHardwareManager()
        self.interfaces = [
            hardware.NetworkInterface('eth0', 'aa:bb:cc:dd:ee:ff'),
            hardware.NetworkInterface('eth1', 'ff:ee:dd:cc:bb:aa')]
        self.lldp_info = {
            'eth0': [
                # Chassis ID
                (1, 'switch1'),
                # Port ID
                (2, '\x05Ethernet1/1'),
                # TTL
                (3, '\x00x'),
                # Port Description
                (4, 'port1'),
                # System Name
                (5, 'switch1'),
            ],
            'eth1': [
                (1, 'switch2'),
                (2, '\x05Ethernet2/1'),
                (3, '\x00x'),
                (4, 'port2'),
                (5, 'switch2'),
            ]
        }

        self.node = {
            'extra': {
                'hardware/interfaces/0/mac_address': 'aa:bb:cc:dd:ee:ff',
                'hardware/interfaces/0/name': 'eth0',
                'hardware/interfaces/0/switch_chassis_id': 'switch1',
                'hardware/interfaces/0/switch_port_id': 'Eth1/1',
                'hardware/interfaces/1/mac_address': 'ff:ee:dd:cc:bb:aa',
                'hardware/interfaces/1/name': 'eth1',
                'hardware/interfaces/1/switch_chassis_id': 'switch2',
                'hardware/interfaces/1/switch_port_id': 'Eth2/1',
            }
        }

        self.ports = [
            {
                'address': 'aa:bb:cc:dd:ee:ff',
                'extra': {
                    'chassis': 'switch1',
                    'port': 'Eth1/1'
                }
            },
            {
                'address': 'ff:ee:dd:cc:bb:aa',
                'extra': {
                    'chassis': 'switch2',
                    'port': 'Eth2/1'
                }
            }
        ]

        self.netiface = {
            17: [{'broadcast': 'ff:ff:ff:ff:ff:ff',
                  'addr': 'aa:bb:cc:dd:ee:ff'}],
            2: [{'broadcast': '10.0.0.255',
                 'netmask': '255.255.255.0',
                 'addr': '10.0.0.2'}],
            10: [{'netmask': 'ffff:ffff:ffff:ffff::',
                  'addr': '2001:4802:7801:102:be76:4eff:fe20:67ae'},
                 {'netmask': 'ffff:ffff:ffff:ffff::',
                  'addr': 'fe80::be76:4eff:fe20:67ae%eth0'}]
        }

        self.port_tuples = set([('switch2', 'eth2/1'), ('switch1', 'eth1/1')])

    @mock.patch('onmetal_ironic_hardware_manager.OnMetalHardwareManager.'
                '_get_node_switchports')
    @mock.patch('onmetal_ironic_hardware_manager.OnMetalHardwareManager.'
                '_get_port_from_lldp')
    @mock.patch('ironic_python_agent.netutils.get_lldp_info')
    @mock.patch('onmetal_ironic_hardware_manager.OnMetalHardwareManager.'
                'list_network_interfaces')
    def test_verify_ports(self, list_mock, lldp_mock,
                          lldp_ports_mock, node_ports_mock):
        list_mock.return_value = self.interfaces
        lldp_mock.return_value = {
            'eth0': self.lldp_info['eth0'],
            'eth1': self.lldp_info['eth1']
        }

        node_ports_mock.return_value = self.port_tuples
        lldp_ports_mock.side_effect = [
            ('switch1', 'eth1/1'),
            ('switch2', 'eth2/1')
        ]

        self.hardware.verify_ports(self.node, self.ports)

    @mock.patch('onmetal_ironic_hardware_manager.OnMetalHardwareManager.'
                '_get_node_switchports')
    @mock.patch('onmetal_ironic_hardware_manager.OnMetalHardwareManager.'
                '_get_port_from_lldp')
    @mock.patch('ironic_python_agent.netutils.get_lldp_info')
    @mock.patch('onmetal_ironic_hardware_manager.OnMetalHardwareManager.'
                'list_network_interfaces')
    def test_verify_ports_mismatch(self, list_mock, lldp_mock,
                                   lldp_ports_mock, node_ports_mock):
        list_mock.return_value = self.interfaces
        lldp_mock.return_value = {
            'eth0': self.lldp_info['eth0'],
            'eth1': self.lldp_info['eth1']
        }

        node_ports_mock.return_value = self.port_tuples
        lldp_ports_mock.side_effect = [
            ('switch1', 'Eth1/2'),  # mismatch port
            ('switch2', 'Eth2/1')
        ]

        self.assertRaises(errors.VerificationFailed,
                          self.hardware.verify_ports,
                          self.node,
                          self.ports)

    @mock.patch('onmetal_ironic_hardware_manager.OnMetalHardwareManager.'
                '_get_node_switchports')
    @mock.patch('onmetal_ironic_hardware_manager.OnMetalHardwareManager.'
                '_get_port_from_lldp')
    @mock.patch('ironic_python_agent.netutils.get_lldp_info')
    @mock.patch('onmetal_ironic_hardware_manager.OnMetalHardwareManager.'
                'list_network_interfaces')
    def test_verify_ports_unmatched(self, list_mock, lldp_mock,
                                    lldp_ports_mock, node_ports_mock):
        list_mock.return_value = self.interfaces
        # Node has more ports than detected
        lldp_mock.return_value = {
            'eth0': self.lldp_info['eth0'],
        }

        node_ports_mock.return_value = self.port_tuples
        lldp_ports_mock.side_effect = [
            ('switch1', 'Eth1/1'),
        ]

        self.assertRaises(errors.VerificationFailed,
                          self.hardware.verify_ports,
                          self.node,
                          self.ports)

    def test__get_tlv_malformed(self):
        self.lldp_info['eth0'][0] = ('bad tlv',)
        self.assertRaises(errors.VerificationError,
                          self.hardware._get_tlv,
                          1,
                          self.lldp_info['eth0'])

    def test__get_port_from_lldp(self):
        expected_ports = ('switch1', 'eth1/1')
        ports = self.hardware._get_port_from_lldp(self.lldp_info['eth0'])
        self.assertEqual(expected_ports, ports)

    def test__get_node_switchports(self):
        expected_ports = set([('switch2', 'eth2/1'), ('switch1', 'eth1/1')])
        ports = self.hardware._get_node_switchports(self.node, self.ports)
        self.assertEqual(expected_ports, ports)
