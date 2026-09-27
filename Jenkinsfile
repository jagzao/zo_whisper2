pipeline {
    agent any

    parameters {
        booleanParam(name: 'RUN_SOAK', defaultValue: false, description: 'Repeat synthetic E2E three times after normal gates')
    }

    environment {
        PYTHONUNBUFFERED = '1'
        ALLOW_EXTERNAL_LLM = 'false'
    }

    stages {
        stage('Bootstrap') {
            steps {
                script {
                    if (isUnix()) {
                        sh 'python -m pip install -e ".[dev]"'
                    } else {
                        bat 'python -m pip install -e ".[dev]"'
                    }
                }
            }
        }

        stage('Targeted') {
            steps {
                script {
                    def cmd = 'python scripts/gate_runner.py targeted tests/test_gate_runner.py tests/test_project_override.py tests/integration/test_dashboard_process_restart.py'
                    if (isUnix()) { sh cmd } else { bat cmd }
                }
            }
        }

        stage('Quality') {
            steps {
                script {
                    if (isUnix()) { sh 'python scripts/gate_runner.py quality' }
                    else { bat 'python scripts/gate_runner.py quality' }
                }
            }
        }

        stage('Security') {
            steps {
                script {
                    if (isUnix()) { sh 'python scripts/gate_runner.py security' }
                    else { bat 'python scripts/gate_runner.py security' }
                }
            }
        }

        stage('Playwright') {
            steps {
                script {
                    if (isUnix()) { sh 'python -m playwright install chromium' }
                    else { bat 'python -m playwright install chromium' }
                }
            }
        }

        stage('SonarQube') {
            steps {
                script {
                    if (!env.SONAR_HOST_URL?.trim()) {
                        echo 'SONAR_STATUS=NOT_CONFIGURED'
                        if (isUnix()) {
                            sh 'mkdir -p artifacts/gates && printf "{\"status\":\"NOT_CONFIGURED\",\"gate\":\"sonarqube\"}\n" > artifacts/gates/sonarqube.json'
                        } else {
                            bat 'if not exist artifacts\\gates mkdir artifacts\\gates'
                            writeFile file: 'artifacts/gates/sonarqube.json', text: '{"status":"NOT_CONFIGURED","gate":"sonarqube"}\n'
                        }
                    } else {
                        if (isUnix()) {
                            sh 'sonar-scanner -Dsonar.host.url="$SONAR_HOST_URL" -Dsonar.token="$SONAR_TOKEN"'
                        } else {
                            bat 'sonar-scanner -Dsonar.host.url="%SONAR_HOST_URL%" -Dsonar.token="%SONAR_TOKEN%"'
                        }
                    }
                }
            }
        }

        stage('Full E2E') {
            steps {
                script {
                    def seed = 'python docs/assets/generate_mock_data.py'
                    def e2e = 'python scripts/gate_runner.py e2e'
                    if (isUnix()) {
                        sh seed
                        sh e2e
                    } else {
                        bat seed
                        bat e2e
                    }
                }
            }
        }

        stage('Optional Soak') {
            when {
                expression { return params.RUN_SOAK }
            }
            steps {
                script {
                    for (int i = 1; i <= 3; i++) {
                        echo "Synthetic E2E soak ${i}/3"
                        if (isUnix()) { sh 'python scripts/gate_runner.py e2e' }
                        else { bat 'python scripts/gate_runner.py e2e' }
                    }
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'artifacts/gates/**', allowEmptyArchive: true
            script {
                if (fileExists('docs/assets/cleanup_mock_data.py')) {
                    if (isUnix()) { sh 'python docs/assets/cleanup_mock_data.py || true' }
                    else { bat 'python docs\\assets\\cleanup_mock_data.py' }
                }
            }
        }
    }
}
