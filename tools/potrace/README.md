# Potrace runtime

- Project: Potrace
- Version: 1.16 (Linux x86-64 distribution, statically linked)
- Source: <https://potrace.sourceforge.net/>
- Distribution directory: `potrace-1.16.linux-x86_64`
- Executable SHA-256: `E2D26F8322A7770A6CCDCF30889503B6C61E27ED8A30F13FC8F340174EB435B0`
- License: GNU General Public License version 2 or later; see `COPYING`.

Version self-check from the package root:

```bash
chmod +x tools/potrace/potrace
./tools/potrace/potrace --version
```

The converter always invokes the bundled executable with the frozen arguments:

```text
potrace <mask.bmp> --svg --output <output.svg> --turdsize 0 --resolution 72
```
