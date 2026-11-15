package id.enviropermit;

import com.fasterxml.jackson.databind.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.stream.Collectors;
import org.semanticweb.HermiT.Reasoner;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;
import org.semanticweb.owlapi.reasoner.OWLReasoner;

/** Stateless JSON file CLI: profile CORE OUTPUT | infer REQUEST RESPONSE. */
public final class ReasoningCli {
  static final ObjectMapper JSON = new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);
  static final Set<String> ARTIFACT_NAMES = Set.of("core-schema.owl", "core-asserted.owl", "core-inferred.owl", "swrl-delta.owl", "final-inferred.owl");

  public static void main(String[] args) {
    try {
      if (args.length != 3) throw new IllegalArgumentException("Usage: profile CORE OUTPUT | infer REQUEST RESPONSE");
      Path input = Path.of(args[1]), output = Path.of(args[2]);
      if (Files.exists(output)) throw new IllegalArgumentException("Refusing to overwrite response: " + output);
      if (args[0].equals("profile")) {
        var report = OwlSupport.profile(new KnowledgeBase(input).core);
        JSON.writeValue(output.toFile(), report);
        if (!(boolean)report.get("in_owl2_dl_profile")) System.exit(2);
      } else if (args[0].equals("infer")) {
        if (ARTIFACT_NAMES.contains(output.getFileName().toString().toLowerCase(Locale.ROOT)))
          throw new IllegalArgumentException("Response path uses a reserved OWL artifact filename");
        for (String artifact : ARTIFACT_NAMES)
          if (Files.exists(output.toAbsolutePath().getParent().resolve(artifact)))
            throw new IllegalArgumentException("Refusing to overwrite inference artifacts in " + output.toAbsolutePath().getParent());
        JSON.writeValue(output.toFile(), infer(JSON.readTree(input.toFile()), output.toAbsolutePath().getParent()));
      } else throw new IllegalArgumentException("Unknown command: " + args[0]);
    } catch (Exception e) {
      System.err.println("REASONER_ERROR: " + e.getMessage());
      e.printStackTrace(System.err);
      System.exit(1);
    }
  }

  static String sha256(byte[] bytes) throws Exception {
    return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
  }

  static void validate(JsonNode request) throws Exception {
    if (!request.required("schema_version").asText().equals("1.1")) throw new IllegalArgumentException("Unsupported schema version");
    if (!request.required("run_rules").isBoolean()) throw new IllegalArgumentException("run_rules must be boolean");
    if (!request.required("max_iterations").isIntegralNumber() || !request.get("max_iterations").canConvertToInt())
      throw new IllegalArgumentException("max_iterations must be integer");
    var facts = request.required("facts"); var context = facts.required("context"); var release = request.required("release");
    if (!context.required("kb_release_id").asText().equals(release.required("id").asText()))
      throw new IllegalArgumentException("KB release/context mismatch");
    Map<String, String> sortedContext = new TreeMap<>();
    for (String key : List.of("assessment_id", "scenario_id", "evidence_snapshot_id", "assessed_on", "kb_release_id")) {
      if (!context.required(key).isTextual()) throw new IllegalArgumentException("Context fields must be strings");
      String value = context.required(key).asText();
      if (value.isBlank()) throw new IllegalArgumentException("Empty context field " + key);
      sortedContext.put(key, value);
    }
    java.time.LocalDate.parse(context.get("assessed_on").asText());
    String namespace = "urn:enviropermit:" + sha256(new ObjectMapper().writeValueAsBytes(sortedContext)) + ":";
    if (!namespace.equals(facts.required("namespace").asText())) throw new IllegalArgumentException("Namespace/context mismatch");
    Set<String> names = new HashSet<>();
    for (String field : List.of("named_candidates", "asserted_triples", "provenance", "closures", "input_issues"))
      if (!facts.required(field).isArray()) throw new IllegalArgumentException(field + " must be array");
    for (var name : facts.required("named_candidates")) {
      if (!name.isTextual() || !name.asText().startsWith(namespace) || !names.add(name.asText()))
        throw new IllegalArgumentException("Duplicate or out-of-snapshot named candidate");
    }
    if (!names.contains(facts.required("project_iri").asText()) || !names.contains(facts.required("assessment_iri").asText()))
      throw new IllegalArgumentException("Project/assessment not in the named candidate set");
    for (var t : facts.required("asserted_triples")) {
      if (!names.contains(t.required("subject").asText())) throw new IllegalArgumentException("Cross-snapshot subject");
      if (!t.hasNonNull("datatype") && !t.required("object").asText().startsWith(OwlSupport.NS)
          && !names.contains(t.get("object").asText())) throw new IllegalArgumentException("Cross-snapshot object");
    }
    Set<Integer> provenanceCoverage = new HashSet<>();
    for (var p : facts.required("provenance")) {
      if (!p.required("context").equals(context)) throw new IllegalArgumentException("Cross-snapshot provenance");
      if (!p.required("fact_index").isIntegralNumber() || !p.get("fact_index").canConvertToInt())
        throw new IllegalArgumentException("Invalid provenance index");
      int index = p.required("fact_index").asInt(-1);
      if (index < 0 || index >= facts.get("asserted_triples").size()) throw new IllegalArgumentException("Invalid provenance index");
      if (!provenanceCoverage.add(index)) throw new IllegalArgumentException("Ambiguous provenance coverage");
      if (p.required("origin").asText().equals("EXPECTED_EFFECT")) throw new IllegalArgumentException("Expected effects are not evidence");
      if (!Set.of("HYPOTHETICAL", "OBSERVED").contains(p.get("origin").asText()))
        throw new IllegalArgumentException("Unsupported evidence origin");
      if (!p.required("evidence_id").isTextual() || p.get("evidence_id").asText().isBlank())
        throw new IllegalArgumentException("Missing evidence identifier");
    }
    if (provenanceCoverage.size() != facts.get("asserted_triples").size())
      throw new IllegalArgumentException("Incomplete provenance coverage");
    for (String key : List.of("knowledge_base")) {
      String expected = release.required("checksums").required(key).asText();
      if (!sha256(Files.readAllBytes(Path.of(release.required(key + "_path").asText()))).equals(expected))
        throw new IllegalArgumentException("Release checksum mismatch: " + key);
    }
    int iterations = request.required("max_iterations").asInt();
    if (iterations < 1 || iterations > 16) throw new IllegalArgumentException("max_iterations outside 1..16");
  }

  static Map<String, Object> infer(JsonNode request, Path output) throws Exception {
    validate(request);
    var facts = request.get("facts"); var release = request.get("release");
    String namespace = facts.get("namespace").asText();
    var knowledge = new KnowledgeBase(Path.of(release.get("knowledge_base_path").asText()));
    var core = knowledge.core;
    var manager = core.getOWLOntologyManager();
    var queries = knowledge.queries;
    Map<String, Object> result = new LinkedHashMap<>();
    Map<String, Object> profiles = new LinkedHashMap<>();
    result.put("schema_version", "1.1"); result.put("context", facts.get("context"));
    result.put("input_issues", facts.get("input_issues")); result.put("profiles", profiles);
    profiles.put("core", OwlSupport.profile(core));
    OwlSupport.save(core, output.resolve("core-schema.owl"));
    if (!valid(profiles, "core")) return quarantine(result, "INVALID_PROFILE", "CORE_NOT_OWL2_DL");
    Set<String> names = new HashSet<>();
    for (var value : facts.get("named_candidates")) {
      String iri = value.asText(); names.add(iri);
      manager.addAxiom(core, OwlSupport.DF.getOWLDeclarationAxiom(OwlSupport.individual(iri)));
    }
    for (var triple : facts.get("asserted_triples")) manager.addAxiom(core, OwlSupport.assertion(triple, core));
    for (var closure : facts.get("closures")) {
      String subject = closure.required("subject").asText(), property = closure.required("predicate").asText();
      if (!names.contains(subject) || !core.containsObjectPropertyInSignature(IRI.create(property))
          || closure.required("evidence_id").asText().isBlank()) throw new IllegalArgumentException("Invalid closure");
      Set<OWLIndividual> members = new HashSet<>();
      for (var value : closure.required("members")) {
        if (!names.contains(value.asText())) throw new IllegalArgumentException("Cross-snapshot closure");
        members.add(OwlSupport.individual(value.asText()));
      }
      OWLClassExpression filler = members.isEmpty() ? OwlSupport.DF.getOWLNothing() : OwlSupport.DF.getOWLObjectOneOf(members);
      manager.addAxiom(core, OwlSupport.DF.getOWLClassAssertionAxiom(
        OwlSupport.DF.getOWLObjectAllValuesFrom(OwlSupport.DF.getOWLObjectProperty(IRI.create(property)), filler),
        OwlSupport.individual(subject)));
    }
    profiles.put("asserted", OwlSupport.profile(core));
    OwlSupport.save(core, output.resolve("core-asserted.owl"));
    if (!valid(profiles, "asserted")) return quarantine(result, "INVALID_PROFILE", "ASSERTIONS_NOT_OWL2_DL");
    Set<OWLAxiom> asserted = new HashSet<>(core.getAxioms());
    Set<OWLAxiom> cumulativeRules = new HashSet<>();
    List<Map<String, Object>> firings = new ArrayList<>();
    OWLReasoner reasoner = new Reasoner.ReasonerFactory().createReasoner(core);
    try {
      if (!reasoner.isConsistent()) return quarantine(result, "INCONSISTENT", "OWL_INCONSISTENT: asserted snapshot quarantined");
      Set<OWLAxiom> materialized = OwlSupport.materialize(reasoner, core);
      Set<OWLAxiom> coreDelta = new HashSet<>(materialized); coreDelta.removeAll(asserted);
      result.put("core_inferred_triples", OwlSupport.triples(coreDelta, namespace));
      var materializedCore = manager.createOntology();
      manager.addAxioms(materializedCore, asserted); manager.addAxioms(materializedCore, materialized);
      OwlSupport.save(materializedCore, output.resolve("core-inferred.owl"));
      manager.removeOntology(materializedCore);
      int iterations = 0;
      if (request.get("run_rules").asBoolean()) {
        boolean converged = false;
        for (int iteration = 1; iteration <= request.get("max_iterations").asInt(); iteration++) {
          iterations = iteration;
          var stage = RuleStage.run(core, materialized, names, knowledge.rules, iteration);
          Set<OWLAxiom> fresh = new HashSet<>(stage.delta()); fresh.removeAll(core.getAxioms());
          if (fresh.isEmpty()) { converged = true; break; }
          cumulativeRules.addAll(fresh); firings.addAll(stage.records());
          reasoner.dispose(); reasoner = null;
          manager.addAxioms(core, fresh);
          profiles.put("post_rules", OwlSupport.profile(core));
          if (!valid(profiles, "post_rules")) return quarantine(result, "INVALID_PROFILE", "RULE_OUTPUT_NOT_OWL2_DL");
          reasoner = new Reasoner.ReasonerFactory().createReasoner(core);
          if (!reasoner.isConsistent()) return quarantine(result, "INCONSISTENT", "OWL_INCONSISTENT: rule output quarantined");
          materialized = OwlSupport.materialize(reasoner, core);
        }
        if (!converged) return quarantine(result, "NONCONVERGENT", "FIXED_POINT_LIMIT");
        profiles.putIfAbsent("post_rules", OwlSupport.profile(core));
      }
      var deltaOntology = manager.createOntology();
      manager.addAxioms(deltaOntology, cumulativeRules);
      OwlSupport.save(deltaOntology, output.resolve("swrl-delta.owl"));
      manager.removeOntology(deltaOntology);
      manager.addAxioms(core, materialized);
      OwlSupport.save(core, output.resolve("final-inferred.owl"));
      Set<OWLAxiom> finalDelta = new HashSet<>(materialized); finalDelta.removeAll(asserted);
      result.put("inferred_triples", OwlSupport.triples(finalDelta, namespace));
      result.put("consistency_status", "CONSISTENT"); result.put("conflicts", List.of());
      result.put("fired_rules", firings); result.put("stage_iterations", iterations);
      project(result, reasoner, core, facts, queries);
      return result;
    } finally { if (reasoner != null) reasoner.dispose(); manager.removeOntology(core); }
  }

  static boolean valid(Map<String, Object> profiles, String key) {
    return Boolean.TRUE.equals(((Map<?, ?>)profiles.get(key)).get("in_owl2_dl_profile"));
  }

  static Map<String, Object> quarantine(Map<String, Object> result, String status, String conflict) {
    result.put("consistency_status", status); result.put("conflicts", List.of(conflict));
    for (String key : List.of("inferred_triples", "core_inferred_triples", "project_obligations", "decisions",
        "precedence", "evidence_gaps", "fired_rules", "source_traces")) result.put(key, List.of());
    result.put("classifications", Map.of()); result.put("stage_iterations", 0);
    return result;
  }

  /** Generic projection: criteria/branch names and missing-evidence keys live in KB. */
  static void project(Map<String, Object> result, OWLReasoner reasoner, OWLOntology core,
                      JsonNode facts, JsonNode queries) {
    Map<String, List<String>> classifications = new TreeMap<>();
    Map<String, Set<String>> typeIRIs = new TreeMap<>();
    List<Map<String, Object>> traces = new ArrayList<>();
    for (var name : facts.get("named_candidates")) {
      var individual = OwlSupport.individual(name.asText());
      var types = reasoner.getTypes(individual, false).getFlattened();
      typeIRIs.put(name.asText(), types.stream().map(c -> c.getIRI().toString()).collect(Collectors.toSet()));
      classifications.put(name.asText(), types.stream().filter(c -> !c.isOWLThing()).map(c -> OwlSupport.shortName(c.getIRI())).sorted().toList());
      for (var c : types) {
        List<String> sources = core.getAnnotationAssertionAxioms(c.getIRI()).stream()
          .filter(a -> a.getProperty().getIRI().toString().equals(OwlSupport.NS + "source_id"))
          .map(a -> ((OWLLiteral)a.getValue()).getLiteral()).sorted().toList();
        if (!sources.isEmpty()) traces.add(Map.of("subject", name.asText(), "conclusion", OwlSupport.shortName(c.getIRI()), "sources", sources));
      }
    }
    result.put("classifications", classifications);
    traces.sort(Comparator.comparing((Map<String, Object> t) -> t.get("subject").toString())
        .thenComparing(t -> t.get("conclusion").toString()));
    result.put("source_traces", traces);
    var obligations = OwlSupport.values(reasoner, facts.get("project_iri").asText(), "projectObligation");
    result.put("project_obligations", obligations.stream().map(s -> OwlSupport.shortName(IRI.create(s))).sorted().toList());
    Set<List<String>> edges = new TreeSet<>(Comparator.comparing(Object::toString));
    for (String scenario : OwlSupport.values(reasoner, facts.get("project_iri").asText(), "hasScenario"))
      for (String edge : OwlSupport.values(reasoner, scenario, "hasPlanEdge"))
        for (String before : OwlSupport.values(reasoner, edge, "edgeBefore"))
          for (String after : OwlSupport.values(reasoner, edge, "edgeAfter"))
            edges.add(List.of(OwlSupport.shortName(IRI.create(before)), OwlSupport.shortName(IRI.create(after))));
    result.put("precedence", edges);
    Set<String> gaps = new TreeSet<>();
    for (var issue : facts.get("input_issues")) gaps.add(issue.asText());
    for (var spec : queries.get("gaps")) {
      for (var entry : typeIRIs.entrySet()) {
        if (!entry.getValue().contains(spec.get("subject_class").asText())) continue;
        String subject = entry.getKey();
        if (spec.has("when_property") && OwlSupport.values(reasoner, subject, spec.get("when_property").asText()).isEmpty()) continue;
        if (spec.has("missing_property") && !OwlSupport.values(reasoner, subject, spec.get("missing_property").asText()).isEmpty()) continue;
        if (spec.has("when_boolean_property") && !hasTrue(reasoner, subject, spec.get("when_boolean_property").asText())) continue;
        if (spec.has("required_boolean_property") && hasTrue(reasoner, subject, spec.get("required_boolean_property").asText())) continue;
        gaps.add(spec.get("missing_evidence").asText());
      }
    }
    List<Map<String, Object>> decisions = new ArrayList<>();
    for (var spec : queries.get("decisions")) {
      for (var entry : typeIRIs.entrySet()) {
        if (!entry.getValue().contains(spec.get("subject_class").asText())) continue;
        List<String> branches = new ArrayList<>();
        for (var branch : spec.get("branches")) if (entry.getValue().contains(branch.asText())) branches.add(OwlSupport.shortName(IRI.create(branch.asText())));
        List<String> missing = branches.isEmpty() ? List.of(spec.get("missing_evidence").asText()) : List.of();
        gaps.addAll(missing);
        decisions.add(Map.of("id", spec.get("id").asText(), "subject_id", entry.getKey(),
          "applicability", branches.isEmpty() ? "UNRESOLVED" : "APPLICABLE", "fulfillment", "UNKNOWN",
          "branches", branches, "evidence_gaps", missing));
      }
    }
    result.put("decisions", decisions); result.put("evidence_gaps", gaps);
  }

  static boolean hasTrue(OWLReasoner reasoner, String subject, String property) {
    return reasoner.getDataPropertyValues(OwlSupport.individual(subject), OwlSupport.DF.getOWLDataProperty(OwlSupport.vocabularyIRI(property)))
      .stream().anyMatch(value -> value.isBoolean() && value.parseBoolean());
  }
}
