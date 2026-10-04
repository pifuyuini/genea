# Bundled Python runtime licenses

Genea.app copies a complete standalone CPython 3.12.11 arm64 runtime supplied
to the builder. This is the same standalone distribution family used by uv.
The builder does not install dependencies or trim the supplied runtime.

The complete original runtime files remain inside `Contents/Resources/Python`,
including Python's PSF license and third-party acknowledgements in
`lib/python3.12/LICENSE.txt`, and the original license notices in bundled
packages such as pip's `*.dist-info` directory. Consult those actual files for
all applicable copyright and license notices.

The build only adjusts Mach-O references and applies local ad hoc signatures;
Python source behavior is unchanged.

The kinship data's complete MIT copyright and license text is preserved under
`Contents/Resources/resources/kinship/LICENSE`.

Official standalone runtime source:
https://github.com/astral-sh/python-build-standalone

Python license reference:
https://docs.python.org/3.12/license.html

This public preview is not notarized or signed with a Developer ID.
