pipeline {
    agent any

    environment {
        // Secrets are injected from Jenkins Credentials, never hard-coded.
        POSTGRES_USER        = credentials('codelens-postgres-user')
        POSTGRES_PASSWORD    = credentials('codelens-postgres-password')
        JWT_SECRET_KEY        = credentials('codelens-jwt-secret')
        HF_TOKEN              = credentials('codelens-hf-token')
        DOCKERHUB_USERNAME = 'aartibhati'
        IMAGE_TAG              = "${env.BUILD_NUMBER}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Backend: Install Dependencies') {
            steps {
                dir('backend') {
                    sh '''
                        rm -rf .venv
                        /var/lib/jenkins/.pyenv/versions/3.11.17/bin/python -m venv .venv
                        . .venv/bin/activate
                        python --version
                        pip install --upgrade pip
                        pip install torch --index-url https://download.pytorch.org/whl/cpu
                        pip install -r requirements.txt
                    '''
                }
            }
        }

        stage('Backend: Lint') {
            steps {
                dir('backend') {
                    sh '''
                        . .venv/bin/activate
                        pip install ruff
                        ruff check app || true
                    '''
                }
            }
        }

        stage('Backend: Test Infra') {
            steps {
                sh '''
                    docker compose -p codelens-ci -f docker-compose.ci.yml up -d postgres redis
        
                    docker compose -p codelens-ci -f docker-compose.ci.yml exec -T postgres sh -c \
                      "until pg_isready -U ${POSTGRES_USER:-codelens}; do sleep 1; done"
        
                    for i in 1 2 3 4 5; do
                        if docker compose -p codelens-ci -f docker-compose.ci.yml exec -T postgres \
                            psql -U ${POSTGRES_USER:-codelens} -tc \
                            "SELECT 1 FROM pg_database WHERE datname = 'codelens_test'" | grep -q 1; then
                            break
                        fi
        
                        echo "Waiting for PostgreSQL to be fully ready... attempt $i/5"
                        sleep 2
                    done
        
                    docker compose -p codelens-ci -f docker-compose.ci.yml exec -T postgres \
                        psql -U ${POSTGRES_USER:-codelens} -tc \
                        "SELECT 1 FROM pg_database WHERE datname = 'codelens_test'" | grep -q 1 || \
                        docker compose -p codelens-ci -f docker-compose.ci.yml exec -T postgres \
                        createdb -U ${POSTGRES_USER:-codelens} codelens_test
                '''
            }
        }

        stage('Backend: Pytest') {
            steps {
                sh '''
                    docker compose -p codelens-ci -f docker-compose.ci.yml run --rm backend-test
                '''
            }
            post {
                always {
                    sh 'docker compose -p codelens-ci -f docker-compose.ci.yml down -v --remove-orphans || true'
                }
            }
        }

        stage('Frontend: Build') {
            steps {
                dir('frontend') {
                    sh '''
                        npm ci
                        npm run build
                    '''
                }
            }
        }

        stage('Docker: Build Images') {
            steps {
                sh '''
                    docker build -t ${DOCKERHUB_USERNAME}/codelens-backend:${IMAGE_TAG} ./backend
                    docker build -t ${DOCKERHUB_USERNAME}/codelens-worker:${IMAGE_TAG} -f docker/worker.Dockerfile .
                    docker build -t ${DOCKERHUB_USERNAME}/codelens-frontend:${IMAGE_TAG} ./frontend
                '''
            }
        }

        stage('Docker: Push Images') {
            steps {
                withCredentials([
                    usernamePassword(
                        credentialsId: 'dockerhub-credentials',
                        usernameVariable: 'DOCKERHUB_USER',
                        passwordVariable: 'DOCKERHUB_TOKEN'
                    )
                ]) {
                    sh '''
                        echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USER" --password-stdin

                        docker push ${DOCKERHUB_USERNAME}/codelens-backend:${IMAGE_TAG}
                        docker push ${DOCKERHUB_USERNAME}/codelens-worker:${IMAGE_TAG}
                        docker push ${DOCKERHUB_USERNAME}/codelens-frontend:${IMAGE_TAG}

                        docker logout
                    '''
                }
            }
        }

        stage('Docker Compose: Validate') {
            steps {
                sh 'docker compose -f docker-compose.prod.yml config -q'
            }
        }

        stage('Ready for Deployment') {
            steps {
                echo "Build ${IMAGE_TAG} passed all checks and is ready for deployment."
                // A real deployment stage would push images to a registry
                // and trigger a rollout, e.g.:
                // sh 'docker tag codelens-backend:${IMAGE_TAG} myregistry/codelens-backend:${IMAGE_TAG}'
                // sh 'docker push myregistry/codelens-backend:${IMAGE_TAG}'
            }
        }
    }

    post {
        always {
            sh 'docker system prune -f || true'
        }
        failure {
            echo 'Pipeline failed - check stage logs above.'
        }
    }
}
