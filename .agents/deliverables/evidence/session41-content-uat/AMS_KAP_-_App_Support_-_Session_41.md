# App Support Session 41

State: READY

## Executive Brief

North America CPRT: Data is exported from Salesforce LEX through SaaS/ETL to fulfilment vendor servers or P&G-hosted database.

PG RegDoc: PG RegDoc is a custom backend application.

## Applications

Facts below describe what was observed in the KT recording. Items marked for live validation are not current-state verification.

## North America CPRT

### Integrations / dependencies

- Data is exported from Salesforce LEX through SaaS/ETL to fulfilment vendor servers or P&G-hosted database. Observed in KT recording at 00:20:51; current state not verified. [Evidence: frame_0021.png]

### Lifecycle

- North America CPRT is in sunset lifecycle status. Observed in KT recording at 00:19:35; current state not verified. [Evidence: seg-02e692baec6d]

### Roles / permissions

- Database access is limited to named PG NA CPRT business, technology development, and operations groups. Observed in KT recording at 00:20:51; current state not verified. [Evidence: frame_0021.png]

### Support / ownership

- Catalogue record lists P&G AMS Support Team as support group. Observed in KT recording at 00:20:51; current state not verified. [Evidence: frame_0021.png]
- Catalogue record lists Paul Senn as owner. Observed in KT recording at 00:20:51; current state not verified. [Evidence: frame_0021.png]

## PG RegDoc

### Architecture / hosting

- PG RegDoc is a custom backend application. Observed in KT recording at 00:01:18; current state not verified. [Evidence: seg-32d4fd721f25]
- PGRegDoc is hosted in Microsoft Azure. Observed in KT recording at 00:01:18; current state not verified. [Evidence: seg-32d4fd721f25, frame_0007.png]
- Private endpoints and virtual networks control network paths to key Azure services. Observed in KT recording at 00:06:28; current state not verified. [Evidence: seg-cfd2ec5be731, frame_0007.png]

### Authentication / access

- PGRegDoc.com uses PingID for authentication. Observed in KT recording at 00:05:41; current state not verified. [Evidence: frame_0005.png]

### Data / storage

- Azure SQL supports data storage. Observed in KT recording at 00:07:35; current state not verified. [Evidence: frame_0007.png]

### Integrations / dependencies

- PG RegDoc uses a SQL database and a mail subscription service. Observed in KT recording at 00:01:23; current state not verified. [Evidence: seg-2425c994a8db]
- Azure Data Factory supports data processing and application operations. Observed in KT recording at 00:07:35; current state not verified. [Evidence: frame_0007.png]

### Operations

- PG RegDoc supports the management of countries, users subscriptions, notifications, text modules, kindarees and so forth. [Evidence: seg-3ad8019ea951]
- Admin employees use a browser to maintain country safety data sheets and export PDFs. [Evidence: frame_0005.png]
- Application developers use a browser for manual application configuration. [Evidence: frame_0005.png]
- Production and development environments are separate. [Evidence: seg-7dc18190442e, frame_0007.png]
- Retailers and consumers use a browser to retrieve available PDF documents. [Evidence: frame_0005.png]
- The application's data classification is public. [Evidence: seg-d98d97108553]
- Users access PGRegDoc securely through web browsers. [Evidence: frame_0007.png]

### Purpose / business context

- PG RegDoc's document sharing capability supports the business requirements associated with REACH. [Evidence: seg-880e2d64c432]

## Architecture / Data Flow

### PG RegDoc data flow

- P&G admin employees -> browser [Evidence: frame_0005.png]
- browser -> PGRegDoc.com [Evidence: frame_0005.png]
- PGRegDoc.com -> browser [Evidence: frame_0005.png]
- browser -> retailers and consumers [Evidence: frame_0005.png]
- Application developers -> browser [Evidence: frame_0005.png]
- browser -> PGRegDoc.com [Evidence: frame_0005.png]
- PGRegDoc.com -- authenticates with -- PingID [Evidence: frame_0005.png]
Observed in recording; source frames: frame_0005.png.

### PG RegDoc technical architecture

- Azure Data Factory -- supports -- processing and application operations [Evidence: frame_0006.png]
- PGRegDoc -- hosts -- Microsoft Azure [Evidence: frame_0006.png]
- Azure SQL -- supports -- data storage [Evidence: frame_0006.png]
- Azure Data Factory -- supports -- data processing and application operations [Evidence: frame_0006.png]
- Private endpoints and virtual networks -- network path control -- key Azure services [Evidence: frame_0006.png]
Observed in recording; source frames: frame_0006.png, frame_0007.png.

### North America CPRT application catalogue record

- Salesforce LEX -> SaaS/ETL application [Evidence: frame_0021.png]
- SaaS/ETL application -> fulfilment vendor servers or P&G-hosted database [Evidence: frame_0021.png]
Observed in recording; source frames: frame_0021.png.

## Open Questions / Needs Review

- The frontend ownership and support boundary remains unconfirmed. [Evidence: E-007]
- Authentication terminology and the current identity provider require confirmation. [Evidence: E-010]
- Application maturity and the incomplete open-source statement require clarification. [Evidence: E-011]
- Detailed technical architecture was not established in this recording. [Evidence: E-012]
- Required resource-group access was not confirmed in this recording. [Evidence: E-015]
- The decommissioning decision remains unresolved. [Evidence: E-021, E-022]

## Glossary

- **SDS**: Safety data sheets, maintained as country-specific documents. [Evidence: frame_0005.png]
- **Azure SQL**: Identified as supporting application data storage. [Evidence: frame_0007.png]
- **Azure Data Factory**: Identified for data processing and application operations. [Evidence: frame_0007.png]
- **PingID**: Named in evidence related to application authentication; current configuration needs validation. [Evidence: frame_0005.png]
- **Salesforce LEX**: Shown as a source in the recorded export flow. [Evidence: frame_0021.png]
- **SaaS/ETL**: Shown as an intermediate application in the recorded export flow. [Evidence: frame_0021.png]


## Evidence Timeline

- 00:00:47-00:01:17 | Session | Opening identifies two applications and names the North America application. | Evidence: E-001
- 00:01:26-00:01:47 | PG RegDoc | PG RegDoc custom backend, P&G Azure (slide), SQL and mail subscription service. | Evidence: E-002
- 00:01:47-00:02:09 | PG RegDoc | Public SDS/technical documents and REACH reference; speaker disclaims REACH familiarity. | Evidence: E-003
- 00:02:09-00:03:25 | PG RegDoc | Subscriptions, notifications, admin functions, and role descriptions. | Evidence: E-005
- 00:04:24-00:04:38 | PG RegDoc | Question and response establish public website support via backend; frontend boundary remains unclear. | Evidence: E-007
- 00:05:07-00:05:41 | PG RegDoc | Manual SDS maintenance/PDF retrieval and developer configuration; data-flow slide. | Evidence: E-008
- 00:05:53-00:06:40 | PG RegDoc | Production/development, Azure SQL, Data Factory, private endpoints and virtual networks. | Evidence: E-009
- 00:06:40-00:07:09 | PG RegDoc | Owner/classification/BIA; authentication term uncertain and IT Access named. | Evidence: E-010
- 00:07:09-00:07:56 | PG RegDoc | Incomplete application maturity/open-source statement. | Evidence: E-011
- 00:08:00-00:09:50 | PG RegDoc | A technical walkthrough was deferred; architecture detail remains incomplete. | Evidence: E-012
- 00:11:53-00:12:45 | North America CPRT | Resource-group access was not confirmed. | Evidence: E-015
- 00:18:23-00:20:34 | North America CPRT | Sunset to leverage optimized; decommissioning undecided. | Evidence: E-021
- 00:20:51-00:20:51 | North America CPRT | Application catalogue screenshot shows app description, lifecycle, access context, and support group. | Evidence: E-020
- 00:23:55-00:35:05 | Session | No transcript segment reaches this final 669.477-second video interval; later sampled frames show gallery only. | Evidence: E-024

## Quality / Evidence Notes

- Measured speech coverage is 97.39%; speech gate: PASS.
- Transcript segments span 68.20% of the full video timeline; media coverage is distinct from speech coverage.
- The final video interval has no transcript coverage; sampled frames in that interval were classified as gallery-only. [Evidence: E-024]
