# LOCAL-CODER-ZMI-DKR-001 — Execution Contract

## Role

You are the implementation worker, not the product analyst.

Read in this order:
1. `AUDIT-ZMI-DKR-001-docker-readiness.md`
2. `US-ZMI-DKR-001-dockerize-product.md`
3. `PLAN-ZMI-DKR-001-docker-implementation.md`
4. `TEST-MATRIX-ZMI-DKR-001.md`

## Model/cost policy

Use the already-paid lightweight GLM coder for normal implementation.

Do not call an expensive planning/reasoning model. Product, architecture, acceptance criteria and test behavior are already frozen in Git.

## Work

- implement PLAN work packages in order;
- write/fix code and required deterministic tests;
- while coding, run only cheap targeted checks relevant to the changed surface;
- do not weaken acceptance tests;
- do not broaden scope.

## Finish

When implementation is complete enough for full validation:

1. run a final cheap syntax/targeted sanity check;
2. commit all intended source/test/docs changes;
3. push the current branch;
4. trigger Jenkins for US-ZMI-DKR-001;
5. record commit SHA + Jenkins build URL/number if immediately available;
6. EXIT.

## Do not

- wait for Jenkins to finish;
- poll Jenkins repeatedly;
- read every Jenkins log;
- enter automatic fix/retest loops after full pipeline results;
- ask owner routine questions;
- decide that a failing acceptance criterion should change;
- deploy/merge.

Pipeline results are reviewed later by owner + heavy model. A new delta plan will be committed if repair work is required.

## Valid blocker

Stop only if implementation cannot proceed because of a true frozen-spec contradiction, destructive external action, unavailable required credential/host service, or an unrecoverable repository state. Report exact evidence without an interactive question loop.
