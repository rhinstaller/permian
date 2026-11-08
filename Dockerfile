FROM quay.io/centos/centos:stream10

# pipeline dependecies
RUN dnf -y install git python3 python3-requests python3-libxml2 python3-pyyaml
# pipeline tests dependecies
RUN dnf -y install https://dl.fedoraproject.org/pub/epel/epel-release-latest-10.noarch.rpm; \
    dnf -y --enablerepo=crb install make python3-pylint diffutils python3-sphinx
# pipeline plugins dependecies
RUN dnf -y install python3-bugzilla beaker-client python3-productmd python3-file-magic python3-flask

# fetch other libraries and tools
WORKDIR /root
RUN git clone https://github.com/rhinstaller/tplib.git

# set up git
RUN git config --global user.email "nobody@example.com"; \
    git config --global user.name "Nobody"
