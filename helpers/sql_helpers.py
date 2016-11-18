def get_pgpro_info(pgpgro_version):
    """

    :param pgpgro_version: string like this:
     ('PostgresPro 9.6.1.1 on x86_64-pc-linux-gnu, compiled by gcc (Debian 4.9.2-10) 4.9.2, 64-bit')
    :return: dict with parsed pgpro_version
    """
    name = pgpgro_version.split()[0]
    version = '.'.join(pgpgro_version.split()[1].split('.')[0:2])
    build = pgpgro_version.split()[1].split('.')[3]
    return {'version': version,
            'name': name,
            'build': build}
