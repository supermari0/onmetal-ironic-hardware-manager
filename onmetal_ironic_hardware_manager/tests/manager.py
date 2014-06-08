import mock
import os
import six

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

    @mock.patch.object(os.path, 'realpath')
    @mock.patch.object(utils, 'execute')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test_erase_block_device_lsi_success(self,
                                            mocked_open,
                                            mocked_execute,
                                            mocked_realpath):
        block_device = hardware.BlockDevice('/dev/sda', 1073741824)

        # Mock out the model detection
        mocked_open.return_value.__enter__ = lambda s: s
        mocked_open.return_value.__exit__ = mock.Mock()
        read_mock = mocked_open.return_value.read
        read_mock.return_value = 'NWD-BLP4-1600\n'

        # Mock the PCI address lookup
        mocked_realpath.return_value = ('/sys/devices/pci0000:00/0000:00:02.0'
            '/0000:02:00.0/host3/target3:1:0/3:1:0:0/block/sdb')

        mocked_execute.side_effect = [
            (DDCLI_LISTALL_OUT, ''),
            (DDCLI_FORMAT_OUT, ''),
        ]
        self.hardware.erase_block_device(block_device)
