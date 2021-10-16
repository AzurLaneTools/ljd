LuaJIT Raw-Bytecode Decompiler (LJD)
===

Based on [Dr-MTN/luajit-decompiler](https://github.com/Dr-MTN/luajit-decompiler)

__WARNING!__ This code is not finished or tested! There is not even
the slightest warranty that the resulting code is even close to the original.
Use the decompiled code at your own risk.

__SECOND WARNING!__ This is all a huge prototype. The "release" version
should be written in Lua itself, because it's cool to
decompile the decompiler — a great test too!


Requirements:
---

Python __3.7+__ from Python.org


How To Use:
---

Use helper functions in `tools.py`, e.g. `set_luajit_version`, `process_bytes`, `process_file`, `process_folder`.

Typical usage:
```python
from ljd.tools import set_luajit_version, process_file

# default version is 21, for LuaJIT-2.0.1
# set version to 20 for LuaJIT-2.0.0
set_luajit_version(20)

process_file('byte-code-path.lj', 'output-path.lua')
```


Licence:
---
Use [GPL licence](LICENSE).

Notification from [Dr-MTN/luajit-decompiler](https://github.com/Dr-MTN/luajit-decompiler):

> The original LJD (and Aussiemon's modifications) are distributed under the MIT licence, and a
> copy of this is included as `LICENSE-upstream`. However, all changes made by myself
> (Campbell "ZNixian" Suter) are licenced under the GNU General Public Licence, version 3 or any later
> version of your choice (a copy of which is available in the `LICENSE` file supplied with the source code).
> 
> I've chosen this license due to certain dynamics of the videogame modding scene for which these changes
> were made. If you have a use for this outside of games, and need a less restrictive licence, please let me know
> and I'll most likely be fine to relicence the project either to MIT or (preferrably) LGPL.
> 
> Also note that while this licence did not appear as my first modification to this project, I did not
> distribute the source before making this change, and never offered those changes under the original licence
> (even if the licence file supplied in those revisions was the original one).
