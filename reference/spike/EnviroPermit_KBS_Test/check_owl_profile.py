"""Run the actual OWLAPI OWL 2 DL profile checker from Owlready2's jar."""
import json
from pathlib import Path
import jpype
import owlready2

jar = Path(owlready2.__file__).parent / 'hermit' / 'HermiT.jar'
jpype.startJVM(classpath=[str(jar)])
Manager = jpype.JClass('org.semanticweb.owlapi.apibinding.OWLManager')
File = jpype.JClass('java.io.File')
Profile = jpype.JClass('org.semanticweb.owlapi.profiles.OWL2DLProfile')
results = []
for path in sorted(Path('outputs').glob('*_asserted.owl')):
    manager = Manager.createOWLOntologyManager()
    ontology = manager.loadOntologyFromOntologyDocument(File(str(path.resolve())))
    report = Profile().checkOntology(ontology)
    results.append({'file':str(path), 'in_owl2_dl_profile':bool(report.isInProfile()),
                    'axioms':ontology.getAxiomCount(),
                    'violations':[str(v) for v in report.getViolations()]})
Path('profile_results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
if not results or not all(r['in_owl2_dl_profile'] for r in results):
    raise SystemExit(1)
