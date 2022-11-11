# Set the base image
FROM ubuntu:20.04 AS builder

ARG TARGETPLATFORM
ARG TARGETARCH

# Print out debug info
RUN printf "I'm building for TARGETPLATFORM=\"${TARGETPLATFORM}\"" && \
    printf ", TARGETARCH=\"${TARGETARCH}\"\n"  && \
    printf "With uname -s : " && uname -s && \
    printf "and  uname -m : " && uname -m && \
    printf "dpkg architecture: $(dpkg --print-architecture)\n"

RUN if [ -z "${TARGETARCH}" ]; then printf "\n\n**********************************************************************************************\n" && \
                                    printf "Argument TARGETARCH not set. Please set either of the following:\n" && \
                                    printf " - enable BuildKit: 'DOCKER_BUILDKIT=1 docker build ...'\n" && \
                                    printf " - use 'docker buildx build...'\n" && \
                                    printf " - set TARGETARCH manually while building: 'docker build --build-arg TARGETARCH=amd64 ...'.\n\n" && \
                                    printf "TARGETARCH can be either amd64 or arm64.\n\n" && \
                                    printf "**********************************************************************************************\n\n" && \
                                    exit 1; \
    fi

# Install linux dependencies
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        build-essential \
        curl \
        gcc \
        git \
        libssl-dev \
        libudev-dev \
        libusb-1.0 \
        pkg-config \
        sudo \
    && rm -rf /var/lib/apt/lists/*

# Add hummingbot user and group
RUN groupadd -g 8211 hummingbot && \
    useradd -m -s /bin/bash -u 8211 -g 8211 hummingbot

# Switch to hummingbot user
USER hummingbot:hummingbot
WORKDIR /home/hummingbot

SHELL [ "/bin/bash", "-lc" ]

# Set path for miniconda
ENV PATH=/home/hummingbot/miniconda3/bin:$PATH
ARG PATH=/home/hummingbot/miniconda3/bin:$PATH

# Install miniconda
RUN case ${TARGETPARCH} in \
         "amd64")  MINICONDA_ARCH=x86_64  ;; \
         "arm64")  MINICONDA_ARCH=aarch64  ;; \
         *)        MINICONDA_ARCH=$(uname -m) ;; \
    esac && \
    curl https://repo.anaconda.com/miniconda/Miniconda3-py38_4.10.3-Linux-${MINICONDA_ARCH}.sh -o ~/miniconda.sh && \
    /bin/bash ~/miniconda.sh -b && \
    rm ~/miniconda.sh && \
    conda init bash && \
    . ~/.bashrc && \
    conda update -n base conda -y && \
    conda clean -tipy


# Install nvm and CeloCLI; note: nvm adds own section to ~/.bashrc
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.35.3/install.sh | bash && \
    export NVM_DIR="/home/hummingbot/.nvm" && \
    source "/home/hummingbot/.nvm/nvm.sh" && \
    nvm install 10 && \
    npm install --only=production -g @celo/celocli@1.0.3 && \
    nvm cache clear && \
    npm cache clean --force && \
    rm -rf /home/hummingbot/.cache

# Copy environment only to optimize build caching, so changes in sources will not cause conda env invalidation
COPY --chown=hummingbot:hummingbot setup/environment-linux-${TARGETARCH}.yml setup/environment-linux.yml

# ./install | create hummingbot environment
RUN conda env create -f setup/environment-linux.yml && \
    conda clean -tipy && \
    # clear pip cache
    rm -rf ~/.cache

# Copy remaining files
COPY --chown=hummingbot:hummingbot bin/ bin/
COPY --chown=hummingbot:hummingbot hummingbot/ hummingbot/
COPY --chown=hummingbot:hummingbot gateway/setup/ gateway/setup/
COPY --chown=hummingbot:hummingbot gateway/src/templates gateway/src/templates
COPY --chown=hummingbot:hummingbot setup.py .
COPY --chown=hummingbot:hummingbot LICENSE .
COPY --chown=hummingbot:hummingbot README.md .
COPY --chown=hummingbot:hummingbot DATA_COLLECTION.md .

# activate hummingbot env when entering the CT
RUN echo "source /home/hummingbot/miniconda3/etc/profile.d/conda.sh && conda activate $(head -1 setup/environment-linux.yml | cut -d' ' -f2)" >> ~/.bashrc

# ./compile + cleanup build folder
RUN /home/hummingbot/miniconda3/envs/$(head -1 setup/environment-linux.yml | cut -d' ' -f2)/bin/python3 setup.py build_ext --inplace -j 8 && \
    rm -rf build/ && \
    find . -type f -name "*.cpp" -delete

# Build final image using artifacts from builer
FROM ubuntu:20.04 AS release
# Dockerfile author / maintainer 
LABEL maintainer="CoinAlpha, Inc. <dev@coinalpha.com>"

# Build arguments
ARG BRANCH=""
ARG COMMIT=""
ARG BUILD_DATE=""
LABEL branch=${BRANCH}
LABEL commit=${COMMIT}
LABEL date=${BUILD_DATE}

# Set ENV variables
ENV COMMIT_SHA=${COMMIT}
ENV COMMIT_BRANCH=${BRANCH}
ENV BUILD_DATE=${DATE}

ENV STRATEGY=${STRATEGY}
ENV CONFIG_FILE_NAME=${CONFIG_FILE_NAME}
ENV WALLET=${WALLET}
ENV CONFIG_PASSWORD=${CONFIG_PASSWORD}

ENV INSTALLATION_TYPE=docker

# Add hummingbot user and group
RUN groupadd -g 8211 hummingbot && \
    useradd -m -s /bin/bash -u 8211 -g 8211 hummingbot

# Create sym links
RUN ln -s /conf /home/hummingbot/conf && \
  ln -s /logs /home/hummingbot/logs && \
  ln -s /data /home/hummingbot/data && \
  ln -s /pmm_scripts /home/hummingbot/pmm_scripts && \
  ln -s /scripts /home/hummingbot/scripts

# Create mount points
RUN mkdir -p /conf /logs /data /pmm_scripts /scripts \
    /gateway-conf \
    /home/hummingbot/.hummingbot-gateway/certs && \
  chown -R hummingbot:hummingbot /conf /logs /data /pmm_scripts /scripts /gateway-conf \
    /home/hummingbot/.hummingbot-gateway
VOLUME /conf /logs /data /pmm_scripts /scripts \
  /gateway-conf \
  /home/hummingbot/.hummingbot-gateway/certs

# Pre-populate pmm_scripts/ volume with default pmm_scripts
COPY --chown=hummingbot:hummingbot pmm_scripts/ pmm_scripts/
# Pre-populate scripts/ volume with default scripts
COPY --chown=hummingbot:hummingbot scripts/ scripts/
# Copy the conf folder structure
COPY --chown=hummingbot:hummingbot conf/ conf/

# Install packages required in runtime
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y sudo libusb-1.0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /home/hummingbot

# Copy all build artifacts from builder image
COPY --from=builder --chown=hummingbot:hummingbot /home/ /home/

# additional configs (sudo)
COPY docker/etc /etc

# Setting bash as default shell because we have .bashrc with customized PATH (setting SHELL affects RUN, CMD and ENTRYPOINT, but not manual commands e.g. `docker run image COMMAND`!)
SHELL [ "/bin/bash", "-lc" ]
CMD /home/hummingbot/miniconda3/envs/$(head -1 setup/environment-linux.yml | cut -d' ' -f2)/bin/python3 bin/hummingbot_quickstart.py \
    --auto-set-permissions $(id -u hummingbot):$(id -g hummingbot)
