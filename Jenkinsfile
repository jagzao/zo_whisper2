def runGate(String command) {
    catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
        if (isUnix()) { sh command } else { bat command }
    }
}

pipeline {
    agent any

    parameters {
        booleanParam(name: 'RUN_SOAK', defaultValue: false, description: 'Repeat Docker E2E three times after normal gates')
    }

    environment {
        PYTHONUNBUFFERED = '1'
        ALLOW_EXTERNAL_LLM = 'false'
    }

    stages {
        stage('Bootstrap') {
            steps {
                script {
                    runGate('python -m pip install -e ".[dev]"')
                }
            }
        }

        stage('Targeted') {
            steps {
                script {
                    runGate('python scripts/gate_runner.py targeted tests/test_gate_runner.py tests/test_summarize_gates.py tests/test_mock_data_root.py tests/test_docker_gate.py tests/test_project_override.py tests/integration/test_dashboard_process_restart.py')
                }
            }
        }

        stage('Full pytest') {
            steps {
                script { runGate('python scripts/gate_runner.py pytest') }
            }
        }

        stage('Quality') {
            steps {
                script { runGate('python scripts/gate_runner.py quality') }
            }
        }

        stage('Security') {
            steps {
                script { runGate('python scripts/gate_runner.py security') }
            }
        }

        stage('Docker config and build') {
            steps {
                script {
                    runGate('python scripts/docker_gate.py docker-config')
                    runGate('python scripts/docker_gate.py docker-build')
                }
            }
        }

        stage('Docker smoke, persistence, ASR') {
            steps {
                script {
                    runGate('python scripts/docker_gate.py docker-smoke')
                    runGate('python scripts/docker_gate.py docker-persistence')
                    runGate('python scripts/docker_gate.py docker-asr-smoke')
                }
            }
        }

        stage('Playwright E2E') {
            steps {
                script {
                    def hostRoot = "${env.WORKSPACE}/artifacts/gates/build-${env.BUILD_NUMBER}/host-e2e-data"
                    withEnv(["ZMI_DATA_ROOT=${hostRoot}", "ZMI_TEST_DATA_ROOT=${hostRoot}", "ZMI_CONFIG_ENV=${hostRoot}/scan_config.env", "ZMI_BASE_URL=http://127.0.0.1:5500", "DASHBOARD_HOST=127.0.0.1", "DASHBOARD_PORT=5500"]) {
                        if (isUnix()) {
                            runGate('mkdir -p "$ZMI_DATA_ROOT" && cp projects.json.example "$ZMI_DATA_ROOT/projects.json"')
                        } else {
                            runGate('if not exist "%ZMI_DATA_ROOT%" mkdir "%ZMI_DATA_ROOT%" && copy /Y projects.json.example "%ZMI_DATA_ROOT%\\projects.json"')
                        }
                        runGate('python docs/assets/generate_mock_data.py')
                        runGate('python scripts/gate_runner.py e2e')
                        runGate('python docs/assets/cleanup_mock_data.py')
                    }
                    runGate('python scripts/docker_gate.py docker-e2e')
                }
            }
        }

        stage('SonarQube') {
            steps {
                script {
                    def reportDir = "artifacts/gates/build-${env.BUILD_NUMBER}"
                    if (isUnix()) { sh "mkdir -p '${reportDir}'" } else { bat "if not exist ${reportDir} mkdir ${reportDir}" }
                    if (!env.SONAR_HOST_URL?.trim()) {
                        echo 'SONAR_STATUS=NOT_CONFIGURED'
                        writeFile file: "${reportDir}/sonarqube.json", text: '{"gate":"sonarqube","status":"NOT_CONFIGURED","check":"SONAR_HOST_URL absent"}\n'
                    } else {
                        def sonarStatus = isUnix()
                            ? sh(returnStatus: true, script: 'sonar-scanner -Dsonar.host.url="$SONAR_HOST_URL" -Dsonar.token="$SONAR_TOKEN"')
                            : bat(returnStatus: true, script: 'sonar-scanner -Dsonar.host.url="%SONAR_HOST_URL%" -Dsonar.token="%SONAR_TOKEN%"')
                        writeFile file: "${reportDir}/sonarqube.json", text: "{\"gate\":\"sonarqube\",\"status\":\"${sonarStatus == 0 ? 'PASS' : 'FAIL'}\",\"check\":\"sonar-scanner\"}\n"
                        if (sonarStatus != 0) {
                            catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') { error('SonarQube scanner failed') }
                        }
                    }
                }
            }
        }

        stage('Optional Docker E2E soak') {
            when { expression { return params.RUN_SOAK } }
            steps {
                script {
                    for (int i = 1; i <= 3; i++) {
                        echo "Docker E2E soak ${i}/3"
                        runGate('python scripts/docker_gate.py docker-e2e')
                        def reportDir = "artifacts/gates/build-${env.BUILD_NUMBER}"
                        def source = "${reportDir}/docker-docker-e2e.json"
                        def target = "${reportDir}/docker-e2e-soak-${i}.json"
                        if (fileExists(source)) {
                            writeFile file: target, text: readFile(source).replace('"gate": "docker-e2e"', '"gate": "docker-e2e-soak-' + i + '"')
                        } else {
                            writeFile file: target, text: '{"gate":"docker-e2e-soak-' + i + '","status":"SKIPPED","check":"gate report unavailable","error_signature":"docker gate did not emit a report"}\n'
                        }
                    }
                }
            }
        }

        stage('Aggregate, archive, notify') {
            steps {
                script {
                    def recipients = env.EMAIL_RECIPIENTS?.trim()
                    def emailStatus = recipients ? 'PENDING' : 'NOT_CONFIGURED'
                    if (!params.RUN_SOAK) {
                        def reportDir = "artifacts/gates/build-${env.BUILD_NUMBER}"
                        if (isUnix()) { sh "mkdir -p '${reportDir}'" } else { bat "if not exist ${reportDir} mkdir ${reportDir}" }
                        writeFile file: "${reportDir}/docker-e2e-soak.json", text: '{"gate":"docker-e2e-soak","status":"SKIPPED","check":"RUN_SOAK=false","error_signature":"optional soak was not requested"}\n'
                    }
                    catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                        def cmd = "python scripts/summarize_gates.py --email-status ${emailStatus}"
                        if (isUnix()) { sh cmd } else { bat cmd }
                    }
                    archiveArtifacts artifacts: 'artifacts/gates/**', allowEmptyArchive: true

                    if (recipients) {
                        try {
                            emailext(
                                to: recipients,
                                subject: "US-ZMI-DKR-001 ${currentBuild.currentResult}: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
                                body: readFile('artifacts/gates/SUMMARY.md') + "\nBuild: ${env.BUILD_URL}",
                                mimeType: 'text/plain'
                            )
                            emailStatus = 'SENT'
                        } catch (Exception ex) {
                            emailStatus = 'NOT_CONFIGURED'
                            echo "EMAIL_STATUS=NOT_CONFIGURED (${ex.class.simpleName})"
                        }
                    }

                    writeFile file: "artifacts/gates/build-${env.BUILD_NUMBER}/EMAIL_STATUS.txt", text: "EMAIL_STATUS=${emailStatus}\n"
                    catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                        def cmd = "python scripts/summarize_gates.py --email-status ${emailStatus}"
                        if (isUnix()) { sh cmd } else { bat cmd }
                    }
                    archiveArtifacts artifacts: 'artifacts/gates/**', allowEmptyArchive: true
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'artifacts/gates/**', allowEmptyArchive: true
        }
    }
}
