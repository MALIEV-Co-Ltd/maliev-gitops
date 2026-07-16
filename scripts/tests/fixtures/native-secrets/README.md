# Native Secret scanner fixtures

These inert `.txt` files contain YAML test inputs. Tests copy them into a temporary Git
repository with `.yaml` or `.yml` extensions. The production scanner evaluates every
tracked YAML file; keeping fixtures as `.txt` prevents test data from weakening policy.

No fixture contains a real credential or secret value.
