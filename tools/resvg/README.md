# resvg runtime

- Project: `linebender/resvg`
- Release: `v0.47.0`
- Asset: `resvg-linux-x86_64.tar.gz`
- Release: <https://github.com/linebender/resvg/releases/tag/v0.47.0>
- Release archive SHA-256: `5C84DCBCD032FE7E8D96E616FD6807A2F9DF6561D2E6582B37E91E63C6CB4FE7`
- Executable SHA-256: `A53A45EAFCAF3C04CEEFC0C150C3D10FDF582D143D1CA5E4A7A64E661C55F02E`
- Runtime: Linux x86-64 with glibc 2.34 or newer
- License: MIT or Apache-2.0 at the user's option; see `LICENSE-MIT` and `LICENSE-APACHE`.

Version self-check from the package root:

```bash
chmod +x tools/resvg/resvg
./tools/resvg/resvg --version
```

The converter always invokes the bundled executable with the frozen arguments:

```text
resvg --dpi 72 <input.svg> <output.png>
```
