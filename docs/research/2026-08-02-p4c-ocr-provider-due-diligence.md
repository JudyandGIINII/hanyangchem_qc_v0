# P4-C OCR Provider 사전 실사

- 조사 기준일: 2026-08-02
- 상태: `RESEARCH ONLY / NOT SELECTED / NOT APPROVED`
- 적용 gate: P4-C `BLOCKED_AP02_PROVIDER_OPT_IN`
- 목적: Provider-specific AP-02 의사결정에 필요한 공개 공식 근거와 미확인 항목을 분리한다.

이 문서는 Provider 선택, 계약·법무 승인, AP-02 승인, 계정·endpoint·credential 존재, 외부 호출 또는 benchmark 실행을 뜻하지 않는다. P4-B도 별도로 `BLOCKED_QUALITY_CORPUS_APPROVAL`이다. 공개 문서의 변경 가능성이 있으므로 실제 의사결정 시점에 공식 자료와 계정·계약 증빙을 다시 확인해야 한다.

## 결론과 권고

### 권고

P4-C의 **첫 검토 후보**로 Azure AI Document Intelligence를 권고한다. 이는 선택 또는 승인이 아니다. AP-02가 나중에 완전하게 승인되는 경우에만 다음의 정확한 시작 범위를 제안한다.

- Provider/model: Azure AI Document Intelligence `prebuilt-layout`
- API 의미론: REST API `2024-11-30`, Document Intelligence 4.0 GA
- 제안 region: Korea Central
- 실행 형태: synchronous/online bounded calls only
- 필수 통제: 요청 수·페이지 수·단가 기반의 애플리케이션 fail-closed hard cap, bounded run 밖 resource/key disabled, 승인된 P4-B corpus와 P4-C payload/destination 범위의 정확한 교집합만 사용

실제 Azure account, tenant, subscription, resource, endpoint, key 또는 Korea Central resource가 존재한다는 주장은 하지 않는다.

### 비교 요약

|순위|후보|공식 기술 근거|주요 governance 제한|현재 결론|
|---:|---|---|---|---|
|1|Azure AI Document Intelligence|Korean Read/Layout, `prebuilt-layout`, 표·title·paragraph·selection mark, 4.0 GA, Korea Central GA, same-region 처리/임시 암호화 저장|training/service-improvement 계약 결과, DPA, subprocessors, account/credential, S0 실제 단가가 `UNKNOWN`|첫 검토 후보, 미선택·미승인|
|2|NAVER Cloud CLOVA OCR|General/Template OCR의 `ko`, V2 권장, General 표 추출|retention/deletion, training use, DPA/subprocessors, 정확한 account region/destination, 안정적 숫자 가격이 `UNKNOWN`|한국어 기술 후보로 강하지만 governance 공개 근거 부족으로 2순위|
|3|Google Document AI|Enterprise OCR/Form Parser/Layout Parser의 한국어·표·layout, processor version pinning, 고객 데이터 비학습 공개 근거|한국 region 없음; 해외 처리·cross-border 승인 필요|3순위|
|제외|AWS Textract|공식 limits가 지원 언어를 English/French/German/Italian/Portuguese/Spanish로만 열거|한국어 미열거|이번 P4-C shortlist에서 제외|

## 1. Azure AI Document Intelligence

### 공식 공개 근거

- [Language support](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr?view=doc-intel-4.0.0)는 Read/Layout 문서 분석의 한국어 지원을 명시한다.
- [Layout model](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0)은 `prebuilt-layout`이 text, tables, titles/headings, paragraphs/document structure, selection marks를 추출하며 Document Intelligence v4.0 `2024-11-30` GA에서 REST API를 지원한다고 설명한다.
- [Version history](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/versioning/changelog-release-history?view=doc-intel-4.0.0)는 GA SDK가 REST API `2024-11-30`을 기본 대상으로 삼는다고 기록한다.
- [Azure products by region](https://azure.microsoft.com/en-us/explore/global-infrastructure/products-by-region/table)의 조사일 표에서 Korea Central의 Azure AI Document Intelligence가 GA로 표시됐다.
- [Data, privacy, and security](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/document-intelligence/data-privacy-security?view=doc-intel-4.0.0)는 입력이 resource 생성 region에서 처리되고, 데이터와 결과가 같은 region의 Azure Storage에 임시 암호화 저장된다고 설명한다. 분석 완료 후 입력/결과는 24시간 뒤 자동 삭제되며, 결과는 `Delete Analyze Result`로 더 일찍 영구 삭제할 수 있다.
- [공개 가격 페이지](https://azure.microsoft.com/en-us/pricing/details/document-intelligence/)는 F0가 월 500페이지까지 무료임을 표시한다. 조사 시 렌더링된 표에는 S0 숫자 단가가 표시되지 않았다.
- [Azure budget 문서](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets)는 budget threshold가 알림을 만들지만 resource에 영향을 주거나 소비를 중지하지 않는다고 명시한다.

### 해석

한국어, 표와 문서 구조, 국내 region, 고정 GA API 의미론을 함께 만족하는 공개 근거가 세 후보 중 가장 직접적이다. 그러나 Azure budget은 hard stop이 아니므로 비용 안전장치로 단독 사용할 수 없다. hard cap은 승인된 단가를 전제로 요청 수·페이지 수·예상 비용을 요청 전 계산하여 초과 시 전송 전에 거부하는 애플리케이션 통제와, bounded run 밖 resource/key 비활성화로 구성해야 한다.

### `UNKNOWN`

- 고객 입력/결과의 training 또는 service-improvement 사용에 관한 실제 적용 계약 결과
- 실제 DPA 검토·수락 결과와 현재 subprocessor 목록
- tenant, account, subscription, credential owner, credential lifecycle
- 실제 resource/endpoint와 Korea Central 배치 증빙
- S0의 적용 통화·계약별 숫자 단가와 benchmark 총예산
- payload allow-list, redaction, logging, deletion 검증, incident owner

## 2. NAVER Cloud CLOVA OCR

### 공식 공개 근거

- [CLOVA OCR 개요](https://api.ncloud-docs.com/docs/ai-application-service-ocr.md)는 General OCR과 Template OCR의 REST interface를 설명한다.
- [General OCR](https://api.ncloud-docs.com/docs/ai-application-service-ocr-ocr.md)은 `lang=ko`, V2 권장, 호출당 하나의 image array, 최대 50 MB를 명시한다. `enableTableDetection`은 domain의 “표 추출 여부” console toggle을 켜야 사용할 수 있다.
- [Template OCR](https://api.ncloud-docs.com/docs/clova-template-ocr-api.md)도 `lang=ko`, V2 권장, 호출당 하나의 image array, 최대 50 MB를 명시한다.
- [CLOVA OCR 제품 페이지](https://www.ncloud.com/product/aiService/ocr)는 CLOVA OCR 제품과 요금 안내 진입점을 제공한다.

### 해석

한국어와 General/Template OCR 지원, 명시적 V2, 선택적 표 구조화 때문에 강한 한국어 기술 후보이다. 다만 조사한 공개 제품/API 문서만으로 Provider governance 필수 항목을 닫을 수 없어 2순위로 둔다.

### `UNKNOWN`

- Provider retention 기간·기산점, 조기 삭제 방법·SLA·증빙
- 고객 데이터의 training/service-improvement 사용과 opt-out
- DPA 수락 결과와 현재 subprocessor 검토
- 실제 account region, processing/storage destination, cross-border 여부
- 실제 계정에 적용되는 안정적 숫자 단가와 hard cost cap
- account, endpoint/domain, credential, payload/log/audit/incident 통제

## 3. Google Document AI

### 공식 공개 근거

- [Language support index](https://docs.cloud.google.com/document-ai/docs/languages)와 [processor list](https://docs.cloud.google.com/document-ai/docs/processors-list)는 Enterprise Document OCR, Form Parser, Layout Parser의 한국어 지원을 열거한다. Form Parser는 table을, Layout Parser는 text/table/list와 context-aware chunk를 추출한다.
- [Enterprise Document OCR](https://docs.cloud.google.com/document-ai/docs/enterprise-document-ocr)는 text/layout 추출과 stable/frozen processor version 사용 가능성을 설명한다. 실제 benchmark가 승인된다면 processor version을 pin해야 한다.
- [Security](https://docs.cloud.google.com/document-ai/docs/security)는 고객 content를 Document AI model training에 사용하지 않는다고 밝힌다. online/synchronous 입력은 memory에서 처리되고 disk에 저장되지 않으며, batch 입력은 일반적으로 처리 직후 삭제되지만 failsafe TTL이 최대 1일이다.
- [Regions](https://docs.cloud.google.com/document-ai/docs/regions)는 `us`/`eu` multi-region과 Mumbai, Singapore, Sydney, London, Frankfurt, Montréal의 제한적 single region을 열거한다. Korea region은 없다.
- [Pricing](https://cloud.google.com/products/document-ai/pricing)의 조사일 공개 가격은 Enterprise OCR의 첫 1,000 pages/month를 무료, 이후 5M까지 USD 1.50/1,000 pages, Form Parser USD 30/1,000, Layout Parser USD 10/1,000으로 표시했다.

### 해석

한국어·표·layout과 공개 데이터 사용 설명, 버전 pinning은 장점이다. 그러나 Korea region이 없어 승인된 payload를 해외 destination으로 전송하는 cross-border 검토가 필요하므로 3순위다.

### `UNKNOWN`

- 실제 사용할 processor와 정확한 pinned version/region 조합
- 실제 DPA 수락·subprocessor·cross-border 법무 결과
- account/project/credential, 적용 통화·세금·계약 가격, budget/hard cap
- payload/redaction/logging/deletion/incident 통제

## 4. AWS Textract 제외 근거

[Amazon Textract 공식 limits](https://docs.aws.amazon.com/textract/latest/dg/limits-document.html)는 text detection 지원 언어를 English, French, German, Italian, Portuguese, Spanish로 열거하며 한국어를 포함하지 않는다. 따라서 이번 한국어 OCR P4-C shortlist에서는 제외한다. 이는 AWS 전체 서비스에 대한 일반 평가가 아니라 해당 공식 제한과 현재 목적에 따른 범위 결정이다.

## 5. P4-B와 로컬 inventory 경계

민감한 로컬 원본의 파일명·경로·hash·body를 기록하지 않고 aggregate만 남긴다.

- candidate documents: 4
- human label evidence가 확인된 eligible 문서: 0
- independent-review evidence가 확인된 eligible 문서: 0
- P4-B eligible: 0

따라서 이 inventory는 비대표적이며 `QUALITY corpus`가 아니다. 외부 benchmark, corpus 품질 또는 representativeness를 주장할 수 없고 P4-B는 `BLOCKED_QUALITY_CORPUS_APPROVAL`로 유지된다.

## 6. 남은 Provider-specific AP-02 gap

다음 항목이 모두 증빙·승인될 때까지 P4-C는 `BLOCKED_AP02_PROVIDER_OPT_IN`이다.

1. 하나의 Provider/model/version/endpoint/region 조합과 실제 account/resource 증빙
2. payload category 및 field allow-list, redaction 방법·검증, request/page bounds
3. retention/deletion/training/abuse-monitoring 조건과 검증 방법
4. DPA, subprocessors, data residency/cross-border, security/privacy 법무 결과
5. credential owner/source/scope/rotation/revocation과 log redaction
6. 적용 숫자 단가, 승인 예산, request/page/unit-cost 기반 fail-closed hard cap
7. audit/raw-response custody/deletion, disable/rollback/manual fallback, incident owner
8. 승인된 P4-B manifest와 P4-C payload/destination의 정확한 교집합
9. Provider-specific approver, 날짜, evidence ID, 최종 `APPROVED` 결정

현재 이 항목들은 모두 `PENDING`이며 실제 Provider selection, legal approval, AP-02 approval, credential, network invocation, deployment 또는 production readiness가 아니다.
