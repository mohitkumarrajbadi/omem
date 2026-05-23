use pyo3::prelude::*;
use numpy::{PyReadonlyArray1, PyReadonlyArray2};
use std::collections::BinaryHeap;
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
    type_boosts: &[f32; 10], // Matching 10 MemoryType enum values
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

#[pyfunction]
fn rag_score_batch(
    query: PyReadonlyArray1<f32>,
    vectors: PyReadonlyArray2<f32>,
    base_scores: PyReadonlyArray1<f32>,
    recencies: PyReadonlyArray1<f32>,
    types: PyReadonlyArray1<u8>,
    weights: [f32; 4],
    type_boosts: [f32; 10],
    top_k: usize,
) -> PyResult<Vec<(usize, f32)>> {
    let q = query.as_slice()?;
    let vs = vectors.as_array();
    let bs = base_scores.as_slice()?;
    let rs = recencies.as_slice()?;
    let ts = types.as_slice()?;

    let mut heap = BinaryHeap::with_capacity(top_k + 1);

    // Parallelize scoring across all cores
    let scored: Vec<ScoredIndex> = (0..bs.len()).into_par_iter().map(|i| {
        let vec_row = vs.row(i).to_slice().unwrap();
        let s = score_memory_simd(q, vec_row, bs[i], rs[i], ts[i], &weights, &type_boosts);
        ScoredIndex { index: i, score: s }
    }).collect();

    // Reduce on main thread
    for item in scored {
        heap.push(item);
        if heap.len() > top_k {
            heap.pop();
        }
    }

    let mut results: Vec<(usize, f32)> = heap.into_sorted_vec().iter()
        .map(|x| (x.index, x.score)).collect();
    results.reverse();
    Ok(results)
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

    // Find indices that should be archived
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

    // Simple O(N^2) for now, but in Rust with Rayon it's very fast
    for i in 0..n {
        if used[i] { continue; }
        let mut cluster = vec![i];
        used[i] = true;

        let row_i = vs.row(i);
        
        for j in (i + 1)..n {
            if used[j] { continue; }
            
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
    let high_re: Vec<Regex> = high_signals.iter().map(|s| Regex::new(s).unwrap()).collect();
    let low_re: Vec<Regex> = low_signals.iter().map(|s| Regex::new(s).unwrap()).collect();

    let results: Vec<f32> = contents.into_par_iter().map(|content| {
        let text = content.to_lowercase();
        
        for re in &high_re {
            if re.is_match(&text) { return 0.85; }
        }
        for re in &low_re {
            if re.is_match(&text) { return 0.25; }
        }
        
        // Length heuristic
        let words = text.split_whitespace().count();
        if words < 3 { 0.3 }
        else if words < 10 { 0.5 }
        else { 0.65 }
    }).collect();

    Ok(results)
}

// ── COGNITION: Conflict Detection ──

#[pyfunction]
fn cognition_detect_conflicts(
    cluster_indices: Vec<Vec<usize>>,
    contents: Vec<String>,
) -> PyResult<Vec<Vec<(usize, usize)>>> {
    let conflict_keywords = ["not", "instead", "changed", "stopped", "no longer", "but"];
    
    let results: Vec<Vec<(usize, usize)>> = cluster_indices.into_par_iter().map(|indices| {
        let mut conflicts = Vec::new();
        for i in 0..indices.len() {
            for j in (i + 1)..indices.len() {
                let c1 = &contents[indices[i]].to_lowercase();
                let c2 = &contents[indices[j]].to_lowercase();
                
                let mut has_conflict = false;
                for kw in &conflict_keywords {
                    if c2.contains(kw) { 
                        // Shared nouns/keywords check omitted for brevity, but could be added here
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
    }).collect();

    Ok(results)
}

#[pymodule]
fn omem_rust(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(rag_score_batch, m)?)?;
    m.add_function(wrap_pyfunction!(cognition_forget_sweep, m)?)?;
    m.add_function(wrap_pyfunction!(cognition_cluster_batch, m)?)?;
    m.add_function(wrap_pyfunction!(cognition_classify_batch, m)?)?;
    m.add_function(wrap_pyfunction!(cognition_detect_conflicts, m)?)?;
    Ok(())
}
