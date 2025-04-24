# Final Plan for Implementing User Behavior Analytics (UBA) - Adapted for FYP Context

## 1. Introduction & Strategy Overview

This document outlines the finalized plan for implementing User Behavior Analytics (UBA) within the Sentinel monitoring system. The goal is to analyze logs collected by SentinelApp clients to detect anomalous user behavior that may indicate security risks, thereby enabling the Risk Scoring feature (#6) and providing data for the User Profiles (#5) and Alerts & Incidents components.

Based on analysis and discussion, the following strategic decisions define this implementation:

### Hybrid Data Storage
We will utilize OpenSearch (deployed on AWS at [OpenSearch Dashboard](https://search-sentinelprimeregistry-re5i27ttwnf44njaayopo6vouq.aos.us-east-1.on.aws/_dashboards)) as the primary, centralized repository for storing raw log data from all monitoring modules. This leverages its strengths in handling high-volume log ingestion, search, and time-series analysis required for UBA. Supabase will be used to store the processed UBA results (calculated risk scores/levels, generated alerts, contributing factors) for efficient integration with the SentinelPrime dashboard and its existing relational data (users, devices).

### Analysis Approach
We will employ Machine Learning (ML) using an unsupervised anomaly detection method, as labeled malicious data is typically unavailable initially. Given the context of this final year project, where access to a target organization for live data collection is not feasible, the initial model training will rely on alternative data sources as detailed in Phase 3, acknowledging the inherent limitations compared to training on organization-specific data.

### Initial Model
The primary algorithm will be Isolation Forest, implemented using the scikit-learn Python library, chosen for its efficiency and effectiveness in identifying outliers in multi-dimensional data.

### Baseline Scope
We will establish per-role baselines. This provides a balance between accuracy (recognizing different job functions have different norms) and manageability (fewer models than per-user). This requires user roles (e.g., Developer, Admin, Standard User) to be defined, either based on the chosen alternative dataset or assigned during data collection/simulation. If roles are unavailable or indistinguishable in the data source, a single global baseline will be the initial fallback, with this limitation documented.

### Training Data Source: 
(See Adaptation in Phase 3) The ideal approach requires training on target organization data. For this project, an alternative source will be used.

### Adaptation Method
The system will adapt to evolving user behavior through periodic batch retraining (demonstrated weekly using the alternative data source) supplemented by an administrator feedback loop within SentinelPrime to help refine alerting.

### Processing Schedule
A batch processing script will run every 15 minutes to analyze recent logs from OpenSearch, generate scores using the trained models, and update results in Supabase, providing reasonably up-to-date risk assessments.

### Dashboard Display
UBA results will be presented in SentinelPrime as a Categorical Risk Level (e.g., Low, Medium, High, Critical) for each user, along with the top contributing anomalous event types that influenced the current score.

---

## 2. Rationale for Key Decisions

- **OpenSearch for Raw Logs:** Optimal for high-volume, semi-structured log data ingestion, complex querying, aggregation, and time-series analysis needed for feature engineering. Facilitates exploration via OpenSearch Dashboards.
  
- **Supabase for Results:** Simplifies integration with the React-based SentinelPrime dashboard, leverages existing Supabase setup, suitable for storing structured, lower-volume UBA outputs (scores, alerts) alongside user/device data.
  
- **Batch Retraining:** Chosen for implementation simplicity and stability within a project scope, compared to the higher complexity of online learning systems. Allows adaptation through scheduled retraining.
  
- **Isolation Forest:** An efficient, standard unsupervised algorithm good for outlier detection without needing labeled anomaly data.
  
- **Per-Role Baselines:** A pragmatic compromise offering better context than a global baseline while being more manageable than per-user models (contingent on role availability in the chosen data source).
  
- **Alternative Training Data Source:** Due to the constraints of this academic project preventing deployment and data collection within a target organization, an alternative data source (public dataset, simulated data, or lab collection) will be used for initial model training and demonstration. This is a necessary adaptation, though it limits the model's initial tuning to real-world, organization-specific nuances.
  
- **Training on Target Data (Ideal vs. Project Reality):** While training on target organization data is non-negotiable for production UBA effectiveness to capture environment-specific norms, this project will utilize [Specify Chosen Alternative Data Source: Public Dataset/Simulated Data/Project Team Data - INSERT HERE] as a substitute for initial training. The limitations of this approach (e.g., potential mismatch in patterns, lack of true organizational context) must be acknowledged. The system architecture, however, is designed assuming future retraining would occur on target-specific data in a real deployment.
  
- **Feedback Loop:** Incorporates human expertise (via admin labeling of alerts) to improve accuracy and reduce alert fatigue over time, even when initially trained on alternative data.
  
- **15-Minute Batch Processing:** Provides a balance between near real-time awareness and the computational load of processing logs.

---

## 3. Final Phased Implementation Plan

### Phase 1: Data Pipeline & Centralization (OpenSearch Focus)

#### Goal:
Consolidate standardized logs from all monitors into the AWS OpenSearch instance.

#### Tasks:
- **Standardize Log Output:** Modify all Python monitoring scripts (e.g., `login_monitor.py`, `process_monitor.py`, `network_monitor.py`, etc.) to output logs as structured JSON.
- **Essential Common Fields:** `timestamp`, `hostname`, `user_identifier`, `monitor_type`, `event_type`, `pid`, `event_details`.
- **Centralized Logging to OpenSearch:** Update all monitors to reliably send their JSON logs to the `sentinel_raw_logs` OpenSearch index.
- **Define OpenSearch Index Mapping:** Create and apply an explicit index mapping for `sentinel_raw_logs` in OpenSearch.

**Tools:** Python (logging, json, requests), OpenSearch/OpenSearch Dashboards.

---

### Phase 2: Data Preprocessing & Feature Engineering (Querying OpenSearch)

#### Goal:
Transform raw logs from OpenSearch into features suitable for the ML model.

#### Tasks:
- **Data Retrieval Script:** Create a Python script to query `sentinel_raw_logs`.
- **Data Cleaning & Transformation:** Use Pandas to clean the data, filter out noise, and normalize timestamps.
- **Feature Engineering:** Create numerical features aggregated over defined time windows (e.g., per user/role per hour).

**Tools:** Python (pandas, numpy, requests), OpenSearch.

---

### Phase 3: Baseline Modeling & Anomaly Detection

#### Goal:
Train per-role Isolation Forest models on [Specify Chosen Alternative Data Source: Public Dataset/Simulated Data/Project Team Data - INSERT HERE] to demonstrate the UBA system's functionality.

#### Tasks:
- **Select Training Data:** Obtain or generate suitable training data, as detailed in the plan.
- **Prepare Data:** Preprocess and engineer features for the selected alternative training data.
- **Train Per-Role Models:** Train Isolation Forest models on data for each defined user role.
- **Develop Anomaly Scoring Function:** Create a Python function that outputs anomaly scores for new data.
- **Threshold Tuning:** Analyze scores and define initial score ranges for Categorical Risk Levels.

**Tools:** Python (scikit-learn, pandas, numpy, joblib).

---

### Phase 4: Integration, Alerting & Refinement (Using Supabase for Results)

#### Goal:
Operationalize UBA scoring using the models trained on alternative data, store results in Supabase, integrate with the dashboard, and enable the feedback loop for demonstration.

#### Tasks:
- **Implement Batch Processing Script:** Develop a Python script to process logs every 15 minutes and update risk scores in Supabase.
- **Dashboard Integration (SentinelPrime):** Modify backend and frontend to display UBA results.
- **Implement Admin Feedback Loop:** Add UI elements for admins to mark alerts as "True Positive" or "False Positive".

**Tools:** Python (pandas, scikit-learn, requests, opensearch-py, supabase-py, schedule/Task Scheduler), Supabase (PostgreSQL), Node.js/Express (Backend), React (Frontend), OpenSearch.

---

## 4. Tooling Summary

- **Log Collection:** Python scripts within SentinelApp (Electron client).
- **Log Aggregation/Storage (Raw):** OpenSearch (AWS Hosted).
- **Log Exploration:** OpenSearch Dashboards (AWS Hosted).
- **Data Processing/Feature Engineering:** Python (pandas, numpy).
- **ML Modeling/Scoring:** Python (scikit-learn, joblib).
- **UBA Results Storage:** Supabase (PostgreSQL).
- **Batch Job Scheduling:** OS Task Scheduler or Python schedule library.
- **Dashboard Backend:** Node.js/Express (SentinelPrime).
- **Dashboard Frontend:** React (SentinelPrime).

---

## 5. Next Steps

1. Begin **Phase 1**: Standardize log formats across all Python monitors and implement reliable sending to the `sentinel_raw_logs` index in your AWS OpenSearch instance.
2. Define the OpenSearch index mapping for `sentinel_raw_logs`.
3. Define user roles within the SentinelPrime/Supabase system (these will be used for modeling based on the alternative data source).
4. Select and prepare your chosen alternative data source (Public Dataset / Simulated Data / Project Team Data) for use in Phase 3.

This finalized plan provides a clear and actionable roadmap for implementing the UBA feature within the context and constraints of your final year project.
