pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 90, unit: 'MINUTES')
    }

    parameters {
        booleanParam(name: 'RUN_SOAK', defaultValue: false, description: 'Run optional soak/nightly checks')
    }

    environment {
        PYTHONPATH = 'src'
    }

    stages {
        stage('Targeted') {
            steps { runTargeted() }
        }
        stage('Quality') {
            steps { runGate('quality') }
        }
        stage('Security') {
            steps { runGate('security') }
        }
        stage('Playwright') {
            steps { runGate('playwright') }
        }
        stage('SonarQube') {
            steps {
                script {
                    if (env.SONAR_HOST_URL?.trim() && env.SONAR_TOKEN?.trim()) {
                        runGate('sonar')
                    } else if (env.SONAR_REQUIRED?.toBoolean()) {
                        error('SonarQube is required but SONAR_HOST_URL or SONAR_TOKEN is not configured')
                    } else {
                        writeFile file: 'artifacts/gates/sonar-status.txt', text: 'NOT_CONFIGURED: set SONAR_HOST_URL and SONAR_TOKEN in Jenkins credentials/environment.\n'
                        echo 'SonarQube: NOT_CONFIGURED'
                    }
                }
            }
        }
        stage('Full E2E') {
            steps { runGate('e2e') }
        }
        stage('Optional soak/nightly') {
            when { expression { return params.RUN_SOAK } }
            steps {
                script {
                    if (isUnix()) {
                        sh 'python -m pytest tests/integration -q'
                    } else {
                        bat 'python -m pytest tests/integration -q'
                    }
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'artifacts/gates/**', allowEmptyArchive: true
            deleteDir()
        }
    }
}

def runGate(String gate) {
    if (isUnix()) {
        sh "python scripts/gate_runner.py ${gate}"
    } else {
        bat "python scripts/gate_runner.py ${gate}"
    }
}

def runTargeted() {
    if (isUnix()) {
        sh 'python scripts/gate_runner.py targeted tests/test_gate_runner.py'
    } else {
        bat 'python scripts/gate_runner.py targeted tests/test_gate_runner.py'
    }
}
