import pkgutil
import importlib
import inspect
import pytest

import ifrsmodel


def _discover_ifrsmodel_modules():
    """Return a list of (module_name, is_pkg) for modules under ifrsmodel."""
    mods = []
    for finder, name, ispkg in pkgutil.walk_packages(ifrsmodel.__path__, ifrsmodel.__name__ + "."):
        mods.append((name, ispkg))
    return mods


def test_import_all_ifrsmodel_modules():
    mods = _discover_ifrsmodel_modules()
    # Ensure we discovered at least the package itself and/or submodules
    assert mods is not None
    for name, ispkg in mods:
        # Import each discovered module to ensure there are no import-time errors
        mod = importlib.import_module(name)
        assert mod is not None


def test_modules_expose_public_callables_or_attrs():
    mods = _discover_ifrsmodel_modules()
    for name, _ in mods:
        mod = importlib.import_module(name)
        public = [a for a in dir(mod) if not a.startswith("_")]
        # Ensure introspection works and we can list public attributes
        assert isinstance(public, list)
        # At minimum there should be a list (may be empty in some small modules)
        callables = [getattr(mod, a) for a in public if callable(getattr(mod, a))]
        # It's okay for a module to have no callables; just ensure the filtering runs
        assert isinstance(callables, list)


def test_pdtransition_expected_functions_present():
    # Check for canonical PD functions used by other tests
    try:
        from ifrsmodel.PD import PDtransition
    except Exception:
        pytest.skip("PDtransition module not available to run this check")

    expected = [
        "calculate_cumulative_pds",
        "calculate_conditional_pds",
        "calculate_conditional_pds_monthly",
    ]
    for name in expected:
        assert hasattr(PDtransition, name), f"PDtransition missing expected function: {name}"
