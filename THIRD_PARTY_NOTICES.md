# Third-party notices

This delivery contains the following third-party runtimes and uses the Python
packages listed in `requirements.txt`.

## Potrace 1.16

- Upstream: <https://potrace.sourceforge.net/>
- Bundled file: `tools/potrace/potrace` (Linux x86-64, statically linked)
- License text: `tools/potrace/COPYING` (GNU GPL version 2 or later)
- Frozen SHA-256: `E2D26F8322A7770A6CCDCF30889503B6C61E27ED8A30F13FC8F340174EB435B0`

## resvg 0.47.0

- Upstream: <https://github.com/linebender/resvg/tree/v0.47.0>
- Release: <https://github.com/linebender/resvg/releases/tag/v0.47.0>
- Release asset: `resvg-linux-x86_64.tar.gz`
- Bundled file: `tools/resvg/resvg` (Linux x86-64)
- License texts: `tools/resvg/LICENSE-MIT` and `tools/resvg/LICENSE-APACHE`
- Release archive SHA-256: `5C84DCBCD032FE7E8D96E616FD6807A2F9DF6561D2E6582B37E91E63C6CB4FE7`
- Frozen executable SHA-256: `A53A45EAFCAF3C04CEEFC0C150C3D10FDF582D143D1CA5E4A7A64E661C55F02E`

## Python runtime dependencies

- NumPy: <https://numpy.org/>
- OpenCV Python wheels: <https://github.com/opencv/opencv-python>
- Pillow: <https://python-pillow.org/>

The Python packages are installed separately with `requirements.txt`; their
source and license metadata are provided by their respective distributions.
