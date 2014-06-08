onmetal-ironic-hardware-manager
===============================

Put this module on the PYTHONPATH of an [Ironic Python
Agent](https://github.com/openstack/ironic-python-agent) to add the
functionality necessary for the agent to handle unusual hardware in OnMetal
flavors.

## Notes:

1. This module requires that `ddcli` be present on `PATH`
2. For some reason related to the `ironic-python-agent` dependency, tests will
   only pass if you run `tox` with the `-r` option.
