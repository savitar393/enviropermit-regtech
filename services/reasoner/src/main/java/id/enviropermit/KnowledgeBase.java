package id.enviropermit;

import com.fasterxml.jackson.databind.node.*;
import java.nio.file.Path;
import java.util.*;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;

/** Read the single authored ontology; isolate SWRL before DL profile/reasoning. */
final class KnowledgeBase {
  record Rule(String id, SWRLRule axiom) {}
  final OWLOntology core;
  final List<Rule> rules = new ArrayList<>();
  final ObjectNode queries = ReasoningCli.JSON.createObjectNode();

  KnowledgeBase(Path path) throws Exception {
    var manager = OWLManager.createOWLOntologyManager();
    core = manager.loadOntologyFromOntologyDocument(path.toFile());
    if (!core.getImportsDeclarations().isEmpty()) throw new IllegalArgumentException("Knowledge base must be self-contained");
    Set<String> identifiers = new HashSet<>();
    for (var rule : core.getAxioms(AxiomType.SWRL_RULE)) {
      boolean enabled = true;
      String id = null;
      int enabledCount = 0, labelCount = 0;
      for (var a : rule.getAnnotations()) {
        if (a.getProperty().getIRI().toString().equals("http://swrl.stanford.edu/ontologies/3.3/swrla.owl#isRuleEnabled")) {
          if (++enabledCount > 1 || !(a.getValue() instanceof OWLLiteral v) || !v.isBoolean()
              || !Set.of("true", "false", "1", "0").contains(v.getLiteral()))
            throw new IllegalArgumentException("Invalid or ambiguous rule annotation: isRuleEnabled");
          enabled = v.parseBoolean();
        }
        if (a.getProperty().isLabel()) {
          if (++labelCount > 1 || !(a.getValue() instanceof OWLLiteral v)
              || !(v.hasLang() || v.getDatatype().getIRI().toString().equals("http://www.w3.org/2001/XMLSchema#string")
                   || v.getDatatype().getIRI().toString().equals("http://www.w3.org/1999/02/22-rdf-syntax-ns#PlainLiteral")))
            throw new IllegalArgumentException("Invalid or ambiguous rule annotation: rdfs:label");
          id = v.getLiteral();
        }
      }
      if (id == null || id.isBlank() || !identifiers.add(id)) throw new IllegalArgumentException("Invalid rule annotation: unique rdfs:label required");
      if (enabled) rules.add(new Rule(id, rule));
    }
    rules.sort(Comparator.comparing(Rule::id));
    manager.removeAxioms(core, new HashSet<>(core.getAxioms(AxiomType.SWRL_RULE)));
    queries.set("decisions", specs("DecisionQuery", Map.of("subjectClass", "subject_class", "missingEvidence", "missing_evidence"), true));
    queries.set("gaps", specs("EvidenceRequirement", Map.of("subjectClass", "subject_class", "missingEvidence", "missing_evidence",
        "whenProperty", "when_property", "missingProperty", "missing_property", "whenBooleanProperty", "when_boolean_property",
        "requiredBooleanProperty", "required_boolean_property"), false));
  }

  private ArrayNode specs(String type, Map<String, String> fields, boolean branches) {
    var rows = ReasoningCli.JSON.createArrayNode();
    List<OWLNamedIndividual> subjects = new ArrayList<>();
    for (var a : core.getClassAssertionAxioms(OwlSupport.cls(type))) subjects.add(a.getIndividual().asOWLNamedIndividual());
    subjects.sort(Comparator.comparing(i -> i.getIRI().toString()));
    for (var subject : subjects) {
      var row = rows.addObject(); row.put("id", OwlSupport.shortName(subject.getIRI()));
      for (var field : fields.entrySet()) {
        List<String> values = annotations(subject.getIRI(), field.getKey());
        if (values.size() > 1) throw new IllegalArgumentException("Ambiguous KB metadata: " + field.getKey());
        if (!values.isEmpty()) row.put(field.getValue(), values.get(0));
      }
      if (!row.has("subject_class") || !row.has("missing_evidence")) throw new IllegalArgumentException("Incomplete KB query metadata");
      if (branches) {
        var values = row.putArray("branches");
        for (var value : annotations(subject.getIRI(), "branchClass")) values.add(value);
        if (values.isEmpty()) throw new IllegalArgumentException("Decision query needs branch classes");
      }
    }
    return rows;
  }

  private List<String> annotations(IRI subject, String property) {
    return core.getAnnotationAssertionAxioms(subject).stream()
      .filter(a -> a.getProperty().getIRI().equals(IRI.create(OwlSupport.NS + property)))
      .map(a -> metadataValue(property, a.getValue()))
      .sorted().toList();
  }

  private String metadataValue(String property, OWLAnnotationValue value) {
    if (property.equals("missingEvidence")) {
      if (!(value instanceof OWLLiteral literal) || literal.getLiteral().isBlank())
        throw new IllegalArgumentException("Missing evidence identifier in KB metadata");
      return literal.getLiteral();
    }
    if (!(value instanceof IRI iri)) throw new IllegalArgumentException("Invalid KB reference: expected IRI for " + property);
    boolean valid = switch (property) {
      case "subjectClass", "branchClass" -> core.containsClassInSignature(iri);
      case "whenProperty", "missingProperty" -> core.containsObjectPropertyInSignature(iri);
      case "whenBooleanProperty", "requiredBooleanProperty" -> core.containsDataPropertyInSignature(iri);
      default -> false;
    };
    if (!valid) throw new IllegalArgumentException("Invalid KB reference: " + property + " " + iri);
    return iri.toString();
  }
}
