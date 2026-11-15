package id.enviropermit;

import java.util.*;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;
import org.swrlapi.factory.SWRLAPIFactory;

/** Generic finite class-head SWRL execution, with per-rule output provenance. */
final class RuleStage {
  record Output(Set<OWLAxiom> delta, List<Map<String, Object>> records) {}
  static Output run(OWLOntology core, Set<OWLAxiom> facts, Set<String> candidates,
                    List<KnowledgeBase.Rule> rules, int iteration) throws Exception {
    Set<OWLAxiom> delta = new HashSet<>();
    List<Map<String, Object>> records = new ArrayList<>();
    for (var spec : rules) {
      var rule = spec.axiom();
      Set<SWRLArgument> bound = new HashSet<>();
      for (var atom : rule.getBody()) {
        if (!(atom instanceof SWRLClassAtom || atom instanceof SWRLObjectPropertyAtom))
          throw new IllegalArgumentException("Supported SWRL bodies: class/object atoms over named individuals");
        bound.addAll(atom.getAllArguments());
      }
      Set<OWLClassExpression> heads = new HashSet<>();
      for (var atom : rule.getHead()) {
        if (!(atom instanceof SWRLClassAtom head) || head.getPredicate().isAnonymous())
          throw new IllegalArgumentException("Supported SWRL heads: named classes");
        if (!bound.contains(head.getArgument())) throw new IllegalArgumentException("Unbound SWRL head argument");
        heads.add(head.getPredicate());
      }
      if (heads.isEmpty()) throw new IllegalArgumentException("SWRL rule needs a head");
      var manager = OWLManager.createOWLOntologyManager();
      var stage = manager.createOntology();
      manager.addAxioms(stage, core.getAxioms(AxiomType.DECLARATION));
      manager.addAxioms(stage, facts);
      manager.addAxiom(stage, rule);
      var engine = SWRLAPIFactory.createSWRLRuleEngine(stage);
      if (!engine.getRuleEngineName().toLowerCase(Locale.ROOT).contains("drools"))
        throw new IllegalStateException("Expected Drools rule engine");
      Set<OWLAxiom> before = new HashSet<>(stage.getAxioms());
      engine.infer();
      Set<OWLAxiom> emitted = new HashSet<>();
      for (var axiom : stage.getAxioms(AxiomType.CLASS_ASSERTION)) {
        if (!before.contains(axiom) && heads.contains(axiom.getClassExpression())) {
          if (!axiom.getIndividual().isNamed() || !candidates.contains(axiom.getIndividual().asOWLNamedIndividual().getIRI().toString()))
            throw new IllegalStateException("SWRL output outside named candidates");
          emitted.add(axiom);
        }
      }
      if (!emitted.isEmpty()) records.add(Map.of("rule_id", spec.id(), "iteration", iteration,
          "conclusions", emitted.stream().map(OwlSupport::triple).sorted(Comparator.comparing(Object::toString)).toList()));
      delta.addAll(emitted);
      manager.removeOntology(stage);
    }
    return new Output(delta, records);
  }
}
