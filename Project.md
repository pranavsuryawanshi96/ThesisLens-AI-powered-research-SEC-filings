# ThesisLens

> **Evidence-backed intelligence from SEC filings**

## 1. Project Overview

**ThesisLens** is an internal AI-powered research assistant designed for equity research analysts.

The application allows analysts to ask questions in natural language about SEC filings and receive answers grounded strictly in the company's filing documents.

Instead of manually reading hundreds of pages across multiple years, analysts can use ThesisLens to quickly find relevant information, compare filings, and verify answers using the original source passages.

---

## 2. Problem Statement

Equity research analysts spend a significant amount of their time reviewing SEC filings such as:

- 10-K
- 10-Q
- Annual reports
- Risk factors
- MD&A
- Business segment information
- Revenue disclosures
- Financial information

The same documents are often reviewed repeatedly by multiple analysts.

This manual intake process is:

- Time-consuming
- Repetitive
- Difficult to scale
- Prone to missing relevant information
- A major bottleneck in analyst productivity

The goal of ThesisLens is to reduce this document-intake burden while maintaining a high level of trust and verifiability.

---

## 3. Goal

Build an internal research assistant that allows analysts to:

1. Ask questions about SEC filings using natural language.
2. Retrieve relevant information from the filing corpus.
3. Generate answers grounded only in available documents.
4. Provide citations for every factual claim.
5. Show the original supporting passage.
6. Identify the filing and page where the information was found.
7. Allow analysts to review their previous conversations.
8. Provide secure browser-based access for authorized users.

---

## 4. Target Users

### Primary Users

- Equity research analysts
- Senior analysts
- Research associates

### Pilot Group

The initial pilot consists of approximately:

- 5 senior analysts

### Future Users

If the pilot succeeds, the application can be expanded to approximately:

- 40 analysts
- Selected research partners

---

## 5. Core Use Case

An analyst should be able to ask:

> "How did Apple's revenue mix change from 2021 to 2025?"

ThesisLens should:

1. Understand the question.
2. Search the relevant SEC filings.
3. Retrieve the most relevant passages.
4. Compare information across years.
5. Generate a concise answer.
6. Provide citations.
7. Show the supporting passages.
8. Allow the analyst to verify the information against the original filing.

---

## 6. Trust Requirements

Trust is the most important requirement of ThesisLens.

### The system MUST:

- Never intentionally invent facts.
- Only answer using information available in the document corpus.
- Provide citations for factual claims.
- Identify the source filing.
- Identify the relevant page.
- Display the supporting passage.
- Clearly indicate when information is unavailable.
- Avoid unsupported conclusions.

### The system SHOULD:

Prefer:

> "The available filings do not provide enough evidence to answer this."

over:

> "I don't know."

A wrong but confident answer is considered worse than no answer.

---

## 7. Corpus

The initial corpus contains SEC filings for major S&P 500 companies.

### Initial Companies

- Apple
- Amazon
- Alphabet
- Microsoft
- NVIDIA

### Initial Years

- 2021
- 2022
- 2023
- 2024
- 2025

### Document Type

Primary:

- 10-K

Future:

- 10-Q
- Other SEC filings

### Source

SEC EDGAR public filings.

No external news, social media, market data, or alternative data should be used for answering questions.

---

## 8. Example Questions

ThesisLens should support questions such as:

### Apple

> How did Apple's revenue mix between iPhone, Services, Mac, iPad, and Wearables change from 2021 to 2025?

### Amazon

> Compare AWS operating income and margin against North America and International from 2021 to 2025.

### NVIDIA

> How did NVIDIA describe demand drivers, customer concentration, and supply constraints for its Data Center business from fiscal 2021 through fiscal 2025?

### Microsoft

> What changed in Microsoft's description of Azure, AI infrastructure, and cloud capacity constraints between 2021 and 2025?

### Alphabet

> How did Google Search, YouTube ads, Google Network, subscriptions/platforms/devices, and Google Cloud revenue trends differ across the available filings?

### Risk Factors

> Which companies materially changed risk-factor language related to AI, cloud infrastructure, export controls, supply chain concentration, or regulation?

---

## 9. Functional Requirements

### 9.1 Document Ingestion

The system should:

- Collect SEC filings.
- Store document metadata.
- Process documents.
- Extract text.
- Preserve page information.
- Split documents into searchable chunks.
- Generate embeddings.
- Store searchable representations.

---

### 9.2 Document Search

The system should:

- Accept natural-language questions.
- Search the document corpus.
- Retrieve relevant passages.
- Support searches across multiple companies.
- Support searches across multiple years.
- Rank relevant passages.

---

### 9.3 Question Answering

The system should:

- Accept natural-language questions.
- Retrieve relevant context.
- Generate an answer based on retrieved context.
- Avoid using information outside the corpus.
- Refuse to answer when sufficient evidence is unavailable.

---

### 9.4 Citations

Every factual answer should provide:

- Company
- Filing type
- Fiscal year
- Source document
- Page number
- Supporting passage

Example:

```text
Source:
Apple Inc. 2025 Form 10-K
Page: 25

Supporting passage:
"..."
```
