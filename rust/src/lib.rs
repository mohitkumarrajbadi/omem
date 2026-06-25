use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::IntoPyDict;
use numpy::{PyArray2, PyReadonlyArray1, PyReadonlyArray2};
use std::collections::{BinaryHeap, HashMap, HashSet};
use std::cmp::Ordering;
use rayon::prelude::*;
use regex::Regex;

#[derive(PartialEq)]
struct ScoredIndex {
    index: usize,
    score: f32,
}

impl Eq for ScoredIndex {}

impl Ord for ScoredIndex {
    fn cmp(&self, other: &Self) -> Ordering {
        other.score.partial_cmp(&self.score).unwrap_or(Ordering::Equal)
    }
}

impl PartialOrd for ScoredIndex {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

#[inline(always)]
pub fn score_memory_simd(
    query: &[f32],
    vector: &[f32],
    base_score: f32,
    recency: f32,
    mem_type: u8,
    weights: &[f32; 4],
    type_boosts: &[f32; 10],
) -> f32 {
    let mut dot = 0.0;
    for i in 0..query.len() {
        dot += query[i] * vector[i];
    }

    let t_boost = if (mem_type as usize) < type_boosts.len() {
        type_boosts[mem_type as usize]
    } else {
        1.0
    };

    (dot * weights[0] + base_score * weights[1] + recency * weights[2]) * t_boost
}

fn lower_tokens(text: &str, stopwords: &HashSet<String>, min_len: usize, max_len: usize) -> Vec<String> {
    let token_re = Regex::new(r"[a-z0-9]{2,}").unwrap();
    let tokens: Vec<String> = token_re
        .find_iter(&text.to_lowercase())
        .map(|m| m.as_str().to_string())
        .filter(|t| t.len() >= min_len && t.len() <= max_len && !stopwords.contains(t))
        .collect();

    let mut terms = Vec::with_capacity(tokens.len() * 2);
    let mut seen = HashSet::new();
    for token in tokens.iter() {
        if seen.insert(token.clone()) {
            terms.push(token.clone());
        }
    }

    for window in tokens.windows(2) {
        if let [first, second] = window {
            let ngram = format!("{} {}", first, second);
            if !stopwords.contains(&ngram) && ngram.len() <= max_len {
                if seen.insert(ngram.clone()) {
                    terms.push(ngram);
                }
            }
        }
    }

    terms
}

#[pyfunction]
#[pyo3(signature = (text, stopwords=None, min_len=2, max_len=64))]
fn tokenize_bm25(
    text: &str,
    stopwords: Option<Vec<String>>,
    min_len: usize,
    max_len: usize,
) -> PyResult<Vec<String>> {
    let stopwords: HashSet<String> = stopwords
        .unwrap_or_default()
        .into_iter()
        .map(|word| word.to_lowercase())
        .collect();
    Ok(lower_tokens(text, &stopwords, min_len, max_len))
}

#[pyfunction]
fn bm25_scores(
    documents: Vec<Vec<String>>,
    query: Vec<String>,
    k1: f32,
    b: f32,
) -> PyResult<Vec<f32>> {
    let n_docs = documents.len() as f32;
    if n_docs == 0.0 {
        return Ok(Vec::new());
    }

    let mut doc_lengths = Vec::with_capacity(documents.len());
    let mut df: HashMap<String, usize> = HashMap::new();
    let mut doc_term_counts: Vec<HashMap<String, usize>> = Vec::with_capacity(documents.len());

    for doc in documents.iter() {
        let mut term_count = HashMap::new();
        for term in doc.iter() {
            *term_count.entry(term.clone()).or_insert(0) += 1;
        }
        for term in term_count.keys() {
            *df.entry(term.clone()).or_insert(0) += 1;
        }
        doc_lengths.push(doc.len() as f32);
        doc_term_counts.push(term_count);
    }

    let avg_length = if doc_lengths.is_empty() {
        1.0
    } else {
        doc_lengths.iter().sum::<f32>() / doc_lengths.len() as f32
    };

    let mut query_terms = HashMap::new();
    for term in query.into_iter() {
        *query_terms.entry(term).or_insert(0) += 1;
    }

    let scores: Vec<f32> = doc_term_counts
        .into_iter()
        .enumerate()
        .map(|(doc_index, term_count)| {
            let doc_len = doc_lengths[doc_index];
            query_terms
                .iter()
                .map(|(term, &q_freq)| {
                    let doc_freq = *term_count.get(term).unwrap_or(&0) as f32;
                    if doc_freq == 0.0 {
                        return 0.0;
                    }

                    let df_count = *df.get(term).unwrap_or(&1) as f32;
                    let idf = ((n_docs - df_count + 0.5) / (df_count + 0.5) + 1.0).max(0.0);
                    let tf = doc_freq;
                    let denom = tf + k1 * (1.0 - b + b * doc_len / avg_length);
                    idf * tf * (k1 + 1.0) / denom * q_freq as f32
                })
                .sum()
        })
        .collect();

    Ok(scores)
}

#[pyfunction]
fn tfidf_query_scores(documents: Vec<String>, query: String) -> PyResult<Vec<f32>> {
    let stopwords = HashSet::new();
    let docs: Vec<Vec<String>> = documents
        .into_iter()
        .map(|doc| lower_tokens(&doc, &stopwords, 2, 64))
        .collect();

    let query_terms = lower_tokens(&query, &stopwords, 2, 64);
    let n_docs = docs.len() as f32;
    let mut df: HashMap<String, usize> = HashMap::new();

    for doc in docs.iter() {
        let unique_terms: HashSet<_> = doc.iter().collect();
        for term in unique_terms {
            *df.entry(term.clone()).or_insert(0) += 1;
        }
    }

    let scores: Vec<f32> = docs
        .into_iter()
        .map(|doc| {
            let mut tf: HashMap<String, usize> = HashMap::new();
            for term in doc {
                *tf.entry(term).or_insert(0) += 1;
            }
            query_terms
                .iter()
                .map(|term| {
                    if let Some(&df_count) = df.get(term) {
                        let idf = ((n_docs / (df_count as f32 + 1.0)).ln() + 1.0).max(0.0);
                        let term_frequency = *tf.get(term).unwrap_or(&0) as f32;
                        term_frequency * idf
                    } else {
                        0.0
                    }
                })
                .sum()
        })
        .collect();

    Ok(scores)
}

#[pyfunction]
fn heuristic_score(
    content: String,
    triggers: Vec<(String, f32)>,
    default_multiplier: f32,
) -> PyResult<f32> {
    let text = content.to_lowercase();
    let mut multiplier = default_multiplier.max(0.0);

    for (pattern, weight) in triggers.into_iter() {
        let re = Regex::new(&pattern).map_err(|err| PyRuntimeError::new_err(err.to_string()))?;
        if re.is_match(&text) {
            multiplier *= weight;
        }
    }

    Ok(multiplier.clamp(0.0, 10.0))
}

#[pyfunction]
fn sleep_cycle(
    importances: PyReadonlyArray1<f32>,
    timestamps: PyReadonlyArray1<f64>,
    access_counts: PyReadonlyArray1<u32>,
    now: f64,
    half_life: f64,
    archive_threshold: f32,
    delete_threshold: f32,
    archive_ttl: f64,
    last_archived: Option<PyReadonlyArray1<f64>>,
) -> PyResult<(Vec<usize>, Vec<usize>)> {
    let imp = importances.as_slice()?;
    let ts = timestamps.as_slice()?;
    let counts = access_counts.as_slice()?;
    // Keep the owning `PyReadonlyArray1` alive for the whole function so the
    // borrowed slice below does not outlive its source.
    let archived_owner = last_archived;
    let archived_at = match &archived_owner {
        Some(arr) => Some(arr.as_slice()?),
        None => None,
    };

    let log_base = 5.0f64;
    let max_usage_boost = 2.0f64;

    let mut archive_indices = Vec::new();
    let mut delete_indices = Vec::new();

    for i in 0..imp.len() {
        let age = (now - ts[i]).max(0.0);
        let recency = 2.0f64.powf(-age / half_life);
        let usage_boost = if counts[i] > 0 {
            (1.0 + counts[i] as f64).log(log_base).min(max_usage_boost)
        } else {
            0.5
        };

        let health = imp[i] as f64 * recency * usage_boost;
        if health < delete_threshold as f64 {
            delete_indices.push(i);
            continue;
        }

        if health < archive_threshold as f64 {
            if let Some(archived) = &archived_at {
                let archive_age = (now - archived[i]).max(0.0);
                if archive_age >= archive_ttl {
                    delete_indices.push(i);
                } else {
                    archive_indices.push(i);
                }
            } else {
                archive_indices.push(i);
            }
        }
    }

    Ok((archive_indices, delete_indices))
}

#[pyfunction]
#[pyo3(signature = (texts, model_name=None))]
fn embed_local_model(
    py: Python,
    texts: Vec<String>,
    model_name: Option<String>,
) -> PyResult<Py<PyArray2<f32>>> {
    let model_name = model_name.unwrap_or_else(|| "all-MiniLM-L6-v2".to_string());
    let sentence_transformers = py.import("sentence_transformers").map_err(|_| {
        PyRuntimeError::new_err(
            "sentence-transformers is required for embed_local_model; install it locally"
        )
    })?;

    let model = sentence_transformers
        .call_method1("SentenceTransformer", (model_name.as_str(),))
        .map_err(|err| PyRuntimeError::new_err(err.to_string()))?;

    let kwargs = [("convert_to_numpy", true), ("show_progress_bar", false)].into_py_dict(py);
    let encoded = model
        .call_method("encode", (texts,), Some(kwargs))
        .map_err(|err| PyRuntimeError::new_err(err.to_string()))?;

    let numpy = py.import("numpy").map_err(|err| PyRuntimeError::new_err(err.to_string()))?;
    let array = numpy
        .getattr("array")?
        .call1((encoded,))?
        .downcast::<PyArray2<f32>>()
        .map_err(|err| PyRuntimeError::new_err(err.to_string()))?;

    Ok(Py::from(array))
}

// ── RAG: batched hybrid scoring (vector + importance + recency + type boost) ──

/// Score a batch of candidate memories against a query and return the
/// top-k `(index, score)` pairs, best first.
///
/// This is the hot path used by `omem.core.engine.rag`. Heavy lifting (the
/// per-row dot products) runs in parallel via rayon; top-k selection uses a
/// bounded min-heap so we never sort the full candidate set.
#[pyfunction]
#[pyo3(signature = (query, vectors, base_scores, recencies, mem_types, weights, type_boosts, top_k))]
fn rag_score_batch(
    query: PyReadonlyArray1<f32>,
    vectors: PyReadonlyArray2<f32>,
    base_scores: PyReadonlyArray1<f32>,
    recencies: PyReadonlyArray1<f32>,
    mem_types: PyReadonlyArray1<u8>,
    weights: Vec<f32>,
    type_boosts: Vec<f32>,
    top_k: usize,
) -> PyResult<Vec<(usize, f32)>> {
    let query = query.as_slice()?;
    let flat = vectors.as_slice()?;
    let base = base_scores.as_slice()?;
    let recency = recencies.as_slice()?;
    let types = mem_types.as_slice()?;

    let n = base.len();
    let dim = query.len();
    if n == 0 || dim == 0 || top_k == 0 {
        return Ok(Vec::new());
    }
    if flat.len() != n * dim {
        return Err(PyRuntimeError::new_err(
            "rag_score_batch: vectors shape does not match query dim / candidate count",
        ));
    }

    // Pack the dynamic weight/boost vectors into the fixed-size arrays the
    // SIMD scorer expects, tolerating shorter inputs gracefully.
    let mut w = [0.0f32; 4];
    for (slot, value) in w.iter_mut().zip(weights.iter()) {
        *slot = *value;
    }
    let mut boosts = [1.0f32; 10];
    for (slot, value) in boosts.iter_mut().zip(type_boosts.iter()) {
        *slot = *value;
    }

    let scores: Vec<f32> = (0..n)
        .into_par_iter()
        .map(|i| {
            let vector = &flat[i * dim..(i + 1) * dim];
            score_memory_simd(query, vector, base[i], recency[i], types[i], &w, &boosts)
        })
        .collect();

    // Bounded min-heap keeps only the top-k highest scores.
    let mut heap: BinaryHeap<ScoredIndex> = BinaryHeap::with_capacity(top_k + 1);
    for (index, &score) in scores.iter().enumerate() {
        heap.push(ScoredIndex { index, score });
        if heap.len() > top_k {
            heap.pop();
        }
    }

    // `ScoredIndex` orders smallest-score-first, so a sorted drain yields
    // best-first ordering for the caller.
    let result = heap
        .into_sorted_vec()
        .into_iter()
        .map(|scored| (scored.index, scored.score))
        .collect();

    Ok(result)
}

// ── COGNITION: Forgetting Engine ──

#[pyfunction]
fn cognition_forget_sweep(
    importances: PyReadonlyArray1<f32>,
    timestamps: PyReadonlyArray1<f64>,
    access_counts: PyReadonlyArray1<u32>,
    now: f64,
    half_life: f64,
    archive_threshold: f32,
) -> PyResult<Vec<usize>> {
    let imp = importances.as_slice()?;
    let ts = timestamps.as_slice()?;
    let counts = access_counts.as_slice()?;

    let log_base = 5.0f64;
    let max_usage_boost = 2.0f64;

    let result: Vec<usize> = (0..imp.len()).into_par_iter()
        .filter(|&i| {
            let age = (now - ts[i]).max(0.0);
            let recency = 2.0f64.powf(-age / half_life);

            let usage_boost = if counts[i] > 0 {
                (1.0 + counts[i] as f64).log(log_base).min(max_usage_boost)
            } else {
                0.5
            };

            let health = imp[i] as f64 * recency * usage_boost;
            health < archive_threshold as f64
        })
        .collect();

    Ok(result)
}

// ── COGNITION: Semantic Clustering ──

#[pyfunction]
fn cognition_cluster_batch(
    vectors: PyReadonlyArray2<f32>,
    threshold: f32,
) -> PyResult<Vec<Vec<usize>>> {
    let vs = vectors.as_array();
    let n = vs.nrows();
    let mut used = vec![false; n];
    let mut clusters = Vec::new();

    for i in 0..n {
        if used[i] {
            continue;
        }
        let mut cluster = vec![i];
        used[i] = true;

        let row_i = vs.row(i);
        for j in (i + 1)..n {
            if used[j] {
                continue;
            }
            let row_j = vs.row(j);
            let mut dot = 0.0;
            for k in 0..row_i.len() {
                dot += row_i[k] * row_j[k];
            }
            if dot >= threshold {
                cluster.push(j);
                used[j] = true;
            }
        }
        if cluster.len() > 1 {
            clusters.push(cluster);
        }
    }

    Ok(clusters)
}

// ── COGNITION: Classifier ──

#[pyfunction]
fn cognition_classify_batch(
    contents: Vec<String>,
    high_signals: Vec<String>,
    low_signals: Vec<String>,
) -> PyResult<Vec<f32>> {
    let high_re: Vec<Regex> = high_signals
        .iter()
        .map(|s| Regex::new(s).unwrap())
        .collect();
    let low_re: Vec<Regex> = low_signals
        .iter()
        .map(|s| Regex::new(s).unwrap())
        .collect();

    let results: Vec<f32> = contents
        .into_par_iter()
        .map(|content| {
            let text = content.to_lowercase();
            for re in &high_re {
                if re.is_match(&text) {
                    return 0.85;
                }
            }
            for re in &low_re {
                if re.is_match(&text) {
                    return 0.25;
                }
            }
            let words = text.split_whitespace().count();
            if words < 3 {
                0.3
            } else if words < 10 {
                0.5
            } else {
                0.65
            }
        })
        .collect();

    Ok(results)
}

// ── COGNITION: Conflict Detection ──

#[pyfunction]
fn cognition_detect_conflicts(
    cluster_indices: Vec<Vec<usize>>,
    contents: Vec<String>,
) -> PyResult<Vec<Vec<(usize, usize)>>> {
    let conflict_keywords = ["not", "instead", "changed", "stopped", "no longer", "but"];
    let results: Vec<Vec<(usize, usize)>> = cluster_indices
        .into_par_iter()
        .map(|indices| {
            let mut conflicts = Vec::new();
            for i in 0..indices.len() {
                for j in (i + 1)..indices.len() {
                    let c2 = &contents[indices[j]].to_lowercase();
                    let mut has_conflict = false;
                    for kw in &conflict_keywords {
                        if c2.contains(kw) {
                            has_conflict = true;
                            break;
                        }
                    }
                    if has_conflict {
                        conflicts.push((indices[i], indices[j]));
                    }
                }
            }
            conflicts
        })
        .collect();

    Ok(results)
}

#[pymodule]
fn omem_rust(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(tokenize_bm25, m)?)?;
    m.add_function(wrap_pyfunction!(bm25_scores, m)?)?;
    m.add_function(wrap_pyfunction!(tfidf_query_scores, m)?)?;
    m.add_function(wrap_pyfunction!(heuristic_score, m)?)?;
    m.add_function(wrap_pyfunction!(sleep_cycle, m)?)?;
    m.add_function(wrap_pyfunction!(embed_local_model, m)?)?;
    m.add_function(wrap_pyfunction!(rag_score_batch, m)?)?;
    m.add_function(wrap_pyfunction!(cognition_forget_sweep, m)?)?;
    m.add_function(wrap_pyfunction!(cognition_cluster_batch, m)?)?;
    m.add_function(wrap_pyfunction!(cognition_classify_batch, m)?)?;
    m.add_function(wrap_pyfunction!(cognition_detect_conflicts, m)?)?;
    Ok(())
}
