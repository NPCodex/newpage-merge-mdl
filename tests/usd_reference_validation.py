"""Optional independent OpenUSD geometry oracle for the bounded USD importer.

Requires usd-core 26.8 in the selected Python environment. This is not a runtime
dependency of the compiler or of the ordinary compatibility regression suite.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--usd-module-path', type=Path)
    args = parser.parse_args()
    if args.usd_module_path:
        sys.path.insert(0, str(args.usd_module_path))
    from pxr import Usd, UsdGeom, Sdf
    sys.argv = [sys.argv[0], str(args.compiler.resolve())]
    import compatibility

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = []

    def compare(case, label, source, model):
        stage = Usd.Stage.Open(str(case.root / source))
        cache = UsdGeom.XformCache()
        expected = []
        for prim in stage.Traverse(Usd.TraverseInstanceProxies()):
            if prim.IsA(UsdGeom.Mesh):
                transform = cache.GetLocalToWorldTransform(prim)
                expected.extend(tuple(round(v, 5) for v in transform.Transform(p))
                                for p in UsdGeom.Mesh(prim).GetPointsAttr().Get())
        expected.sort()

        def vertices(name):
            return sorted(tuple(round(v, 5) for v in p) for p in case.scene_positions(name))

        observed = vertices(model)
        target = output / label
        target.mkdir(exist_ok=True)
        for item in case.root.rglob('*.usda'):
            destination = target / item.relative_to(case.root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
        stage.Flatten().Export(str(target / 'openusd-flattened.usda'))
        Sdf.Layer.FindOrOpen(str(case.root / source)).Export(str(case.root / 'openusd-authored.usdc'))
        case.scene_qc('$modelname authored\n$UpAxis z assimp\n$body m openusd-authored.usdc\n')
        authored = vertices('authored')
        shutil.copy2(case.root / 'openusd-authored.usdc', target / 'openusd-authored.usdc')
        stage.Flatten().Export(str(case.root / 'openusd-flat.usdc'))
        case.scene_qc('$modelname flat\n$UpAxis z assimp\n$body m openusd-flat.usdc\n')
        flattened = vertices('flat')
        shutil.copy2(case.root / 'openusd-flat.usdc', target / 'openusd-flattened.usdc')
        results.append(dict(test=label, openusd_version=Usd.GetVersion(), match=observed == expected,
                            authored_usdc_match=authored == expected, flattened_usdc_match=flattened == expected,
                            expected_world_vertices=expected, actual_world_vertices=observed))

    cases = [
        ('test_usd_nested_references_keep_instances_local_children_and_dependencies', 'instances.usda', 'usdrefs'),
        ('test_usd_variant_selection_and_internal_reference_transform', 'selected.usda', 'variant'),
        ('test_usd_variant_set_authored_order_controls_strength', 'ordered-variants.usda', 'orderedusd'),
        ('test_usd_reference_active_and_extended_variant_selection', 'extended.usda', 'extendedusd'),
        ('test_usd_add_references_expand_undefined_prototypes_once', 'prototype.usda', 'prototypeusd'),
        ('test_usd_instanceable_references_ignore_direct_local_child_opinions', 'instances.usda', 'usdinstance'),
        ('test_usd_reference_reset_transform_stack_is_world_relative', 'reset.usda', 'resetusd'),
    ]
    for method, source, model in cases:
        case = compatibility.Compatibility(method)
        case.setUp()
        try:
            getattr(case, method)()
            compare(case, method, source, model)
            if model == 'variant':
                compare(case, 'internal_reference', 'internal.usda', 'internal')
            if model == 'extendedusd':
                compare(case, 'reference_reactivation', 'reactivate.usda', 'reactivateusd')
                compare(case, 'reference_inherited_inactive', 'inherited-inactive.usda', 'inheritedinactiveusd')
        except Exception as error:
            results.append(dict(test=method, error=str(error)))
        finally:
            case.tearDown()
    for value in ('inherited', 'false', 'true'):
        case = compatibility.Compatibility('test_usd_inherited_instanceable_and_local_false_override')
        case.setUp()
        try:
            case.test_usd_inherited_instanceable_and_local_false_override()
            text = (case.root / 'inherited.usda').read_text()
            case.write('inherited.usda', text.replace('instanceable = true',
                       '' if value == 'inherited' else 'instanceable = ' + value))
            case.scene_qc('$modelname inheritedusd\n$UpAxis z assimp\n$body m inherited.usda\n')
            compare(case, 'inherited_instanceable_' + value, 'inherited.usda', 'inheritedusd')
        except Exception as error:
            results.append(dict(test='inherited_instanceable_' + value, error=str(error)))
        finally:
            case.tearDown()
    (output / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    passed = all(item.get('match') and item.get('authored_usdc_match') and item.get('flattened_usdc_match')
                 for item in results)
    print(json.dumps(dict(openusd_version=Usd.GetVersion(), cases=len(results), passed=passed,
                          results=str(output / 'results.json'))))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
