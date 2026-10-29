# AMS KAP - App Support - Session 41

State: READY

## Executive Brief

NA_CPRT_PANELIST_PAYMENTS: Data is exported from Salesforce LEX through SaaS/ETL to fulfilment vendor servers or P&G-hosted database.

PG_REGDOC: PG_REGDOC shares safety data sheets and other public non-confidential technical documents with consumers and customers through an external website.

## Applications

Facts below describe what was observed in the KT recording. Items marked for live validation are not current-state verification.

## NA_CPRT_PANELIST_PAYMENTS

### Integrations / dependencies

- Data is exported from Salesforce LEX through SaaS/ETL to fulfilment vendor servers or P&G-hosted database. Observed in KT recording at 00:20:51; current state not verified. [Evidence: frame_0021.png]

### Lifecycle

- NA_CPRT_PANELIST_PAYMENTS is in sunset lifecycle status. Observed in KT recording at 00:19:35; current state not verified. [Evidence: seg-b89c18ed9fba]
- Application catalogue records lifecycle as Leverage/Optimize. Observed in KT recording at 00:20:48; current state not verified. [Evidence: seg-1ebd2e8fdfb3, frame_0021.png]

### Operations

- Application catalogue classifies the application sub-category as Business Application. [Evidence: frame_0021.png]

### Roles / permissions

- Database access is limited to named PG NA CPRT business, technology development, and operations groups. Observed in KT recording at 00:20:51; current state not verified. [Evidence: frame_0021.png]

### Support / ownership

- Application catalogue lists P&G AMS Support Team as the support group. Observed in KT recording at 00:20:51; current state not verified. [Evidence: frame_0021.png]
- Application catalogue lists Paul Senn as owner. Observed in KT recording at 00:20:51; current state not verified. [Evidence: frame_0021.png]

## PG_REGDOC

### Architecture / hosting

- PG_REGDOC is a custom backend application. Observed in KT recording at 00:01:18; current state not verified. [Evidence: seg-e07ce32ef381]
- PGRegDoc is hosted in Microsoft Azure. Observed in KT recording at 00:01:18; current state not verified. [Evidence: seg-e07ce32ef381, seg-53b0b78bac34, frame_0007.png]
- Private endpoints and virtual networks control network paths to key Azure services. Observed in KT recording at 00:06:28; current state not verified. [Evidence: seg-080cc93ff0d9, frame_0007.png]
- Production and development environments are separate. Observed in KT recording at 00:07:35; current state not verified. [Evidence: frame_0007.png]

### Authentication / access

- PGRegDoc.com uses PingID for authentication. Observed in KT recording at 00:05:41; current state not verified. [Evidence: frame_0005.png]

### Data / storage

- Azure SQL supports data storage. Observed in KT recording at 00:07:35; current state not verified. [Evidence: frame_0007.png]

### Integrations / dependencies

- PG_REGDOC uses a SQL database and a mail subscription service. Observed in KT recording at 00:01:23; current state not verified. [Evidence: seg-7fb398dc7183]
- Azure Data Factory supports data processing and application operations. Observed in KT recording at 00:06:14; current state not verified. [Evidence: seg-23904847bcc2, frame_0007.png]

### Operations

- PG_REGDOC supports the management of countries, user subscriptions, notifications, text modules. [Evidence: seg-c23115a1db50]
- Admin employees use a browser to maintain country safety data sheets and export PDFs. [Evidence: frame_0005.png]
- Application developers use a browser for manual application configuration. Observed in KT recording at 00:05:41; current state not verified. [Evidence: frame_0005.png]
- Overall business impact assessment is low. Observed in KT recording at 00:06:55; current state not verified. [Evidence: seg-6dfe26aa1aab]
- Retailers and consumers use a browser to retrieve available PDF documents. [Evidence: frame_0005.png]
- The application's data classification is public. Observed in KT recording at 00:06:52; current state not verified. [Evidence: seg-624582bb311e]
- Users access PGRegDoc securely through web browsers. [Evidence: frame_0007.png]

### Purpose / business context

- PG_REGDOC shares safety data sheets and other public non-confidential technical documents with consumers and customers through an external website. [Evidence: seg-0b2b2146c79b]
- PG_REGDOC's document sharing capability supports the business requirements associated with REACH. [Evidence: seg-7cfd8de74550]

### Roles / permissions

- PG_REGDOC provides external access to public safety data sheets and technical documents and supports subscriptions and email notifications. Observed in KT recording at 00:01:59; current state not verified. [Evidence: seg-0c197fbac840]
- Administrative functions are limited according to each user's assigned role and responsibilities. Observed in KT recording at 00:03:09; current state not verified. [Evidence: seg-2e0384674a39, seg-f2005936f429, seg-03ff3cd5313a]
- Consumers and customers access public safety documents and may subscribe to documentation notifications. Observed in KT recording at 00:02:48; current state not verified. [Evidence: seg-0101f268480a, seg-f1d22ff53bad, seg-e086d8bbc01e, seg-f298292a5ae6]
- Global administrators manage countries, user subscriptions, notifications, and text modules. Observed in KT recording at 00:03:03; current state not verified. [Evidence: seg-e086d8bbc01e, seg-2e0384674a39, seg-f298292a5ae6]
- Local administrators manage products and categories. Observed in KT recording at 00:03:17; current state not verified. [Evidence: seg-f298292a5ae6, seg-0efe55106526, seg-f2005936f429]

### Support / ownership

- Application owner was identified as Miguel Angel Moreno Fernandez. Observed in KT recording at 00:06:49; current state not verified. [Evidence: seg-40b6ddd0a020]
- The public website remains within support scope through its supported backend. Observed in KT recording at 00:04:24; current state not verified. [Evidence: E-007]

## Architecture / Data Flow

### 2. Data Flow

- P&G admin employees -> browser [Evidence: frame_0005.png]
- browser -> PGRegDoc.com [Evidence: frame_0005.png]
- PGRegDoc.com -> browser [Evidence: frame_0005.png]
- browser -> retailers and consumers [Evidence: frame_0005.png]
- Application developers -> browser [Evidence: frame_0005.png]
- browser -> PGRegDoc.com [Evidence: frame_0005.png]
- PGRegDoc.com -- authenticates with -- PingID [Evidence: frame_0005.png]
Observed in recording; source frames: frame_0005.png.

### 3. Technical Overview

- Azure Data Factory -- supports -- processing and application operations [Evidence: frame_0006.png]
- PGRegDoc -- hosts -- Microsoft Azure [Evidence: frame_0006.png]
- Azure SQL -- supports -- data storage [Evidence: frame_0006.png]
- Azure Data Factory -- supports -- data processing and application operations [Evidence: frame_0006.png]
- Private endpoints and virtual networks -- network path control -- key Azure services [Evidence: frame_0006.png]
Observed in recording; source frames: frame_0006.png, frame_0007.png.

### Application - North America Central Product Research Testing Panelist Payments

- Salesforce LEX -> SaaS/ETL application [Evidence: frame_0021.png]
- SaaS/ETL application -> fulfilment vendor servers or P&G-hosted database [Evidence: frame_0021.png]
Observed in recording; source frames: frame_0021.png.

## Open Questions / Needs Review

- PG_REGDOC: The frontend ownership and support boundary remains unconfirmed. [Evidence: E-007]
- PG_REGDOC: Authentication provider wording and the named IT Access user-management relationship require confirmation. [Evidence: E-010]
- PG_REGDOC: Application maturity and the incomplete open-source statement require clarification. [Evidence: E-011]
- PG_REGDOC: Detailed technical architecture was not established in this recording. [Evidence: E-012]
- NA_CPRT_PANELIST_PAYMENTS: Required resource-group access was not confirmed in this recording. [Evidence: E-015]
- NA_CPRT_PANELIST_PAYMENTS: Detailed technical architecture was not established in this recording. [Evidence: E-017]
- NA_CPRT_PANELIST_PAYMENTS: The decommissioning decision remains unresolved. [Evidence: E-021, E-022]

## Glossary

- **SDS**: Safety data sheets, maintained as country-specific documents. [Evidence: frame_0005.png, , ]
- **Azure SQL**: Identified as supporting application data storage. [Evidence: frame_0007.png]
- **Azure Data Factory**: Identified for data processing and application operations. [Evidence: , frame_0007.png]
- **PingID**: Named in evidence related to application authentication; current configuration needs validation. [Evidence: frame_0005.png]
- **Salesforce LEX**: Shown as a source in the recorded export flow. [Evidence: frame_0021.png]
- **SaaS/ETL**: Shown as an intermediate application in the recorded export flow. [Evidence: frame_0021.png]


## Evidence Timeline

- 00:00:47-00:01:17 | Session | Opening identifies two applications and names the North America application. | Evidence: E-001
- 00:01:26-00:01:47 | PG_REGDOC | PG RegDoc custom backend, P&G Azure (slide), SQL and mail subscription service. | Evidence: E-002
- 00:01:47-00:02:09 | PG_REGDOC | Public SDS/technical documents and REACH reference; speaker disclaims REACH familiarity. | Evidence: E-003
- 00:02:09-00:03:25 | PG_REGDOC | Subscriptions, notifications, admin functions, and role descriptions. | Evidence: E-005
- 00:04:24-00:04:38 | PG_REGDOC | Question and response establish public website support via backend; frontend boundary remains unclear. | Evidence: E-007
- 00:05:07-00:05:41 | PG_REGDOC | Manual SDS maintenance/PDF retrieval and developer configuration; data-flow slide. | Evidence: E-008
- 00:05:53-00:06:40 | PG_REGDOC | Production/development, Azure SQL, Data Factory, private endpoints and virtual networks. | Evidence: E-009
- 00:06:40-00:07:09 | PG_REGDOC | Owner/classification/BIA; authentication term uncertain and IT Access named. | Evidence: E-010
- 00:07:09-00:07:56 | PG_REGDOC | Incomplete application maturity/open-source statement. | Evidence: E-011
- 00:08:00-00:09:50 | PG_REGDOC | A technical walkthrough was deferred; architecture detail remains incomplete. | Evidence: E-012
- 00:11:53-00:12:45 | NA_CPRT_PANELIST_PAYMENTS | Resource-group access was not confirmed. | Evidence: E-015
- 00:18:23-00:20:34 | NA_CPRT_PANELIST_PAYMENTS | Sunset to leverage optimized; decommissioning undecided. | Evidence: E-021
- 00:20:51-00:20:51 | NA_CPRT_PANELIST_PAYMENTS | Application catalogue screenshot shows app description, lifecycle, access context, and support group. | Evidence: E-020
- 00:23:55-00:35:05 | Session | No transcript segment reaches this final 669.477-second video interval; later sampled frames show gallery only. | Evidence: E-024

## Quality / Evidence Notes

- Measured speech coverage is 97.39%; speech gate: PASS.
- Transcript segments span 68.20% of the full video timeline; media coverage is distinct from speech coverage.
- The final video interval has no transcript coverage; sampled frames in that interval were classified as gallery-only. [Evidence: E-024]
