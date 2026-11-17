#!/bin/sh
#
# Copyright © 2015-2021 the original authors.
#
APP_NAME="Gradle"
APP_BASE_NAME=$(basename "$0")
DEFAULT_JVM_OPTS='"-Xmx64m" "-Xms64m"'
CLASSPATH=$APP_HOME/gradle/wrapper/gradle-wrapper.jar
# ... (полный стандартный скрипт gradlew слишком длинный, см. альтернативу ниже)