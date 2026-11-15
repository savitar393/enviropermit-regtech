package id.enviropermit;

import com.fasterxml.jackson.databind.JsonNode;
import java.nio.file.Path;
import java.util.*;
import java.util.stream.Collectors;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.formats.FunctionalSyntaxDocumentFormat;
import org.semanticweb.owlapi.model.*;
import org.semanticweb.owlapi.profiles.OWL2DLProfile;
import org.semanticweb.owlapi.reasoner.OWLReasoner;

/** OWL conversion and actual profile checking, independent of domain branches. */
final class OwlSupport {
  static final String NS = "https://example.org/enviropermit#";
  static final String TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
  static final String DIFFERENT = "http://www.w3.org/2002/07/owl#differentFrom";
  static final OWLDataFactory DF = OWLManager.getOWLDataFactory();

  static OWLNamedIndividual individual(String iri) { return DF.getOWLNamedIndividual(IRI.create(iri)); }
  static OWLClass cls(String name) { return DF.getOWLClass(IRI.create(NS + name)); }
  static IRI vocabularyIRI(String name) { return IRI.create(name.contains(":") ? name : NS + name); }
  static OWLObjectProperty prop(String name) { return DF.getOWLObjectProperty(vocabularyIRI(name)); }
  static String shortName(IRI iri) { return iri.toString().substring(iri.toString().lastIndexOf('#') + 1); }

  static Map<String, Object> profile(OWLOntology ontology) {
    var report = new OWL2DLProfile().checkOntology(ontology);
    List<String> violations = report.getViolations().stream().map(Object::toString).sorted().collect(Collectors.toList());
    if (!ontology.getAxioms(AxiomType.SWRL_RULE).isEmpty()) violations.add("SWRL rules are forbidden in the core OWL 2 DL stage");
    return Map.of("in_owl2_dl_profile", violations.isEmpty(), "violations", violations,
                  "axiom_count", ontology.getAxiomCount());
  }

  static void save(OWLOntology ontology, Path path) throws Exception {
    ontology.getOWLOntologyManager().saveOntology(ontology, new FunctionalSyntaxDocumentFormat(), IRI.create(path.toUri()));
  }

  static OWLAxiom assertion(JsonNode t, OWLOntology core) {
    var s = individual(t.required("subject").asText());
    String p = t.required("predicate").asText(), o = t.required("object").asText();
    if (p.equals(TYPE)) {
      if (!core.containsClassInSignature(IRI.create(o))) throw new IllegalArgumentException("Unknown class: " + o);
      return DF.getOWLClassAssertionAxiom(DF.getOWLClass(IRI.create(o)), s);
    }
    if (p.equals(DIFFERENT)) return DF.getOWLDifferentIndividualsAxiom(s, individual(o));
    if (t.hasNonNull("datatype")) {
      if (!core.containsDataPropertyInSignature(IRI.create(p))) throw new IllegalArgumentException("Unknown data property: " + p);
      return DF.getOWLDataPropertyAssertionAxiom(DF.getOWLDataProperty(IRI.create(p)), s,
          DF.getOWLLiteral(o, DF.getOWLDatatype(IRI.create(t.get("datatype").asText()))));
    }
    if (!core.containsObjectPropertyInSignature(IRI.create(p))) throw new IllegalArgumentException("Unknown object property: " + p);
    return DF.getOWLObjectPropertyAssertionAxiom(DF.getOWLObjectProperty(IRI.create(p)), s, individual(o));
  }

  /** Materialize only named individuals, never introduce existential witnesses. */
  static Set<OWLAxiom> materialize(OWLReasoner reasoner, OWLOntology ontology) {
    Set<OWLAxiom> result = new HashSet<>();
    for (var i : ontology.getIndividualsInSignature()) {
      for (var c : reasoner.getTypes(i, false).getFlattened())
        if (!c.isOWLThing()) result.add(DF.getOWLClassAssertionAxiom(c, i));
      for (var p : ontology.getObjectPropertiesInSignature())
        for (var o : reasoner.getObjectPropertyValues(i, p).getFlattened())
          result.add(DF.getOWLObjectPropertyAssertionAxiom(p, i, o));
      for (var p : ontology.getDataPropertiesInSignature())
        for (var v : reasoner.getDataPropertyValues(i, p)) result.add(DF.getOWLDataPropertyAssertionAxiom(p, i, v));
    }
    return result;
  }

  static Map<String, Object> triple(OWLAxiom axiom) {
    Map<String, Object> t = new LinkedHashMap<>();
    if (axiom instanceof OWLClassAssertionAxiom a && !a.getClassExpression().isAnonymous() && a.getIndividual().isNamed()) {
      t.put("subject", a.getIndividual().asOWLNamedIndividual().getIRI().toString());
      t.put("predicate", TYPE); t.put("object", a.getClassExpression().asOWLClass().getIRI().toString());
    } else if (axiom instanceof OWLObjectPropertyAssertionAxiom a && !a.getProperty().isAnonymous()) {
      t.put("subject", a.getSubject().asOWLNamedIndividual().getIRI().toString());
      t.put("predicate", a.getProperty().asOWLObjectProperty().getIRI().toString());
      t.put("object", a.getObject().asOWLNamedIndividual().getIRI().toString());
    } else if (axiom instanceof OWLDataPropertyAssertionAxiom a) {
      t.put("subject", a.getSubject().asOWLNamedIndividual().getIRI().toString());
      t.put("predicate", a.getProperty().asOWLDataProperty().getIRI().toString());
      t.put("object", a.getObject().getLiteral());
      t.put("datatype", a.getObject().getDatatype().getIRI().toString());
    } else return null;
    t.putIfAbsent("datatype", null);
    return t;
  }

  static List<Map<String, Object>> triples(Set<OWLAxiom> axioms, String namespace) {
    return axioms.stream().map(OwlSupport::triple).filter(Objects::nonNull)
      .filter(t -> t.get("subject").toString().startsWith(namespace))
      .sorted(Comparator.comparing(Object::toString)).collect(Collectors.toList());
  }

  static List<String> values(OWLReasoner reasoner, String subject, String property) {
    return reasoner.getObjectPropertyValues(individual(subject), prop(property)).getFlattened().stream()
      .map(i -> i.getIRI().toString()).sorted().collect(Collectors.toList());
  }
}
