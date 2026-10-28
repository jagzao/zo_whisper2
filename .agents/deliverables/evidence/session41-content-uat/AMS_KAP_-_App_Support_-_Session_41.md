# App Support Session 41

State: READY

## Executive Brief

North America CPRT: Record describes Salesforce LEX data export through SaaS/ETL to fulfilment vendor servers or P&G-hosted database

PG RegDoc: custom backend, P&G Azure (slide), SQL and mail subscription service.

## Applications

## North America CPRT

### Authentication / access

- North America CPRT: Presenter reports no resource-group permission. [Evidence: E-015]
- North America CPRT: Attempt to switch to AMS Admin account/retrieve access; 74.78-second speech gap occurs in this interval. [Evidence: E-018]
- North America CPRT: Application catalogue screenshot shows app description, lifecycle, access context, and support group. [Evidence: E-020]

### Operational notes

- North America CPRT: Participant advises trying AMS Admin identity; result not shown. [Evidence: E-016]

### Data / storage

- North America CPRT: Data floor/code/scripts, access problem, and no prepared slides. [Evidence: E-017]
- Catalogue record lists Paul Senn as owner [Evidence: frame_0021.png]
- Catalogue record lists P&G AMS Support Team as support group [Evidence: frame_0021.png]
- Database access is limited to named PG NA CPRT business, technology development, and operations groups [Evidence: frame_0021.png]

### Support / lifecycle

- North America CPRT: Sunset to leverage optimized; decommissioning undecided. [Evidence: E-021]
- North America CPRT: Limited tickets/use impression and future decommission request expectation. [Evidence: E-022]

### Architecture / hosting

- Record describes Salesforce LEX data export through SaaS/ETL to fulfilment vendor servers or P&G-hosted database [Evidence: frame_0021.png]
- Salesforce LEX -> SaaS/ETL application -> fulfilment vendor servers or P&G-hosted database [Evidence: frame_0021.png]

## PG RegDoc

### Architecture / hosting

- PG RegDoc: custom backend, P&G Azure (slide), SQL and mail subscription service. [Evidence: E-002]
- PG RegDoc: Production/development, Azure SQL, Data Factory, private endpoints and virtual networks. [Evidence: E-009]
- So this is a custom backend application hosted on PNG Azure. [Evidence: seg-50d0a83c6bc1]
- PGRegDoc is hosted in Microsoft Azure [Evidence: frame_0007.png]
- Private endpoints and virtual networks control network paths to key Azure services [Evidence: frame_0007.png]
- Production and development environments are separate [Evidence: frame_0007.png]

### Operational notes

- PG RegDoc: Public SDS/technical documents and REACH reference; speaker disclaims REACH familiarity. [Evidence: E-003]
- Retailers and consumers use a browser to retrieve available PDF documents [Evidence: frame_0005.png]
- Application developers use a browser for manual application configuration [Evidence: frame_0005.png]
- PGRegDoc.com -> browser -> retailers and consumers: retrieve available documents as PDFs [Evidence: frame_0005.png]
- Application developers -> browser -> PGRegDoc.com: manual configuration [Evidence: frame_0005.png]

### Integrations / dependencies

- PG RegDoc: Subscriptions, notifications, admin functions, and role descriptions. [Evidence: E-005]
- And then this application uses a SQL database and a mail subscription service. [Evidence: seg-ff3193b8d76a]

### Data / storage

- PG RegDoc: Manual SDS maintenance/PDF retrieval and developer configuration; data-flow slide. [Evidence: E-008]
- Admin employees use a browser to maintain country safety data sheets and export PDFs [Evidence: frame_0005.png]
- P&G admin employees -> browser -> PGRegDoc.com: maintain country safety data sheets [Evidence: frame_0005.png]

### Authentication / access

- PG RegDoc: Owner/classification/BIA; authentication term uncertain and IT Access named. [Evidence: E-010]
- PGRegDoc.com uses PingID for authentication [Evidence: frame_0005.png]
- PGRegDoc.com <-> PingID: authentication [Evidence: frame_0005.png]
- Users access PGRegDoc securely through web browsers [Evidence: frame_0007.png]

### Purpose / business context

- Azure SQL supports data storage [Evidence: frame_0007.png]
- Azure Data Factory supports data processing and application operations [Evidence: frame_0007.png]
- Azure SQL provides data storage [Evidence: frame_0007.png]
- Azure Data Factory supports processing and application operations [Evidence: frame_0007.png]

## Ambiguities / Needs Review

- PG RegDoc: Question and response establish public website support via backend; frontend boundary remains unclear. - session41-current-engine-content-uat @ 264.0

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
- 00:08:00-00:09:50 | PG RegDoc | Technical presentation deferred; presenter says not prepared and lacks access. | Evidence: E-012
- 00:11:53-00:12:45 | North America CPRT | Presenter reports no resource-group permission. | Evidence: E-015
- 00:12:46-00:13:18 | North America CPRT | Participant advises trying AMS Admin identity; result not shown. | Evidence: E-016
- 00:15:00-00:16:20 | North America CPRT | Data floor/code/scripts, access problem, and no prepared slides. | Evidence: E-017
- 00:16:42-00:18:40 | North America CPRT | Attempt to switch to AMS Admin account/retrieve access; 74.78-second speech gap occurs in this interval. | Evidence: E-018
- 00:18:23-00:20:34 | North America CPRT | Sunset to leverage optimized; decommissioning undecided. | Evidence: E-021
- 00:20:34-00:20:50 | North America CPRT | Limited tickets/use impression and future decommission request expectation. | Evidence: E-022
- 00:20:50-00:20:56 | North America CPRT | Source wording flagged for review. | Evidence: E-023
- 00:20:51-00:20:51 | North America CPRT | Application catalogue screenshot shows app description, lifecycle, access context, and support group. | Evidence: E-020
- 00:23:55-00:35:05 | Session | No transcript segment reaches this final 669.477-second video interval; later sampled frames show gallery only. | Evidence: E-024
