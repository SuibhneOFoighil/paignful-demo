FROM mambaorg/micromamba:0.15.3

USER root
RUN mkdir /opt/vivek2024
RUN chmod -R 777 /opt/vivek2024
WORKDIR /opt/vivek2024

USER micromamba
COPY environment.yml environment.yml
RUN micromamba install -y -n base -f environment.yml && \
   micromamba clean --all --yes

COPY run.sh run.sh
COPY project_contents project_contents

RUN apt-get update && apt-get install -y mpv

USER root
RUN chmod a+x run.sh

CMD ["./run.sh"]