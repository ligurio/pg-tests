# PostgreSQL regression tests

Этот репозиторий содержит тесты для PostgreSQL и скрипты для их запуска.

## Общее описание и решаемые задачи

Фреймворк выполняется две большие задачи:

    Подготовка окружения для тестирования
    Параметризация и запуск тестов

## Поддерживается запуск тестов через скрипт testrun.py и напрямую с помощью pytest.

Скрипт testrun.py используется для запуска локальных тестов, pytest может использоваться как для запуска локальных тестов, так и для запуска тестов на удаленных физических серверах и виртуальных машинах.

Запуск тестов с помощью testrun.py

Образа виртуалок для тестов лежат находятся webdav﻿﻿.

На всех виртуалках настроен доступ по ssh для пользователей root:TestRoot1 и test:TestPass1, для пользователя test поддерживается режим sudo.

Для Windows 2012 создан пользователь test с правами Admin. Для пользователя "Администратор" выставлен пароль TestRoot1

Запуск локальных тестов с использованием скрипта testrun.py:

-h – помощь

Опции, которые относятся к продукту

--branch –  установка пакетов из бранчи  с указанием имени бранчи

--product_name – имя продукта, доступные значения: postgresql, postgrespro

--product_edition – тип продукта, доступные значения: std, ent, std-cert, ent-cert

--product_version – версия продукта

--product_milestone – статус продукта, доступные значения: beta, либо не задается, если нужна установка из основного репозитория

--skip_install – не устанавливать инстанс postgresql, подразумевается, что уже есть установленная вресия postgresql. значения:

--target – операционная система, на которой будет проводится тестирование

--keep – удалить или сохранить виртуальную машину после выполнения тестов

--export – сохранять ли результаты тестирования в виде отчета

--test – имена тестов, которые будут выполнены (опциональный параметр, если не задан, будут выполнены все тесты из каталога tests/)

## Функции скрипта testrun.py

    Скрипт командной строки
    Развертывание виртуалок
    Запуск ansible playbook для установки пакетов на тестируемой виртуалке
    Заливка фреймворка тестирования на виртуалку
    Запуск тестов на виртуалке
    Получение отчетности


## Запуск локальных тестов с помощью pytest.

Данный вариант подходит для отладки тестов. Чтобы запустить тесты с помощью pytest нужно залить фреймворк на виртуалку, подключиться консольно или по ssh на виртуалку, перейти в директорию с тестами и запустить pytest.

Поддерживаемые параметры:

--product_name – имя продукта, доступные значения: postgresql, postgrespro

--product_edition – тип продукта, доступные значения: std, ent, std-cert, ent-cert

--product_version – версия продукта

--product_milestone – статус продукта, доступные значения: beta, либо не задается, если нужна установка из основного репозитория

--skip_install – не устанавливать инстанс postgresql, подразумевается, что уже есть установленная вресия postgresql. значения:

--target – операционная система, на которой будет проводится тестирование

--keep – удалить или сохранить виртуальную машину после выполнения тестов

--export – сохранять ли результаты тестирования в виде отчета

Так же поддерживаются все дополнительные параметры, которые есть в pytest.


## Запуск тестов без заливки фреймворка на виртуальную машину.

Нужен для запуска кластерных тестов (multimaster, replica). Так же этот запуск более просто в обслуживании, в этот режим можно и удобно писать одиночные тесты (не требующие кластера).

После выполнения тестов виртуальные машины удаляются.

Запуск тестов: перейти в директорию с тестами и выполнить команду: pytest tests_ssh/test [options]

Поддерживаемые опции:

--target – операционная система, на которой будут запускаться тесты, невозможно использование с опцией config

--product_name – имя продукта, доступные значения: postgresql, postgrespro

--product_edition – тип продукта, доступные значения: std, ent, std-cert, ent-cert

--product_version – версия продукта

--product_milestone – статус продукта, доступные значения: beta, либо не задается, если нужна установка из основного репозитория

--branch –  установка пакетов из бранчи  с указанием имени бранчи

--config –  путь для  установки из конфигурационного файла, невозможно использование с опцией target. Конфигурационный файл должен иметь расширение *.ini.

Пример конфигурационного файла config.ini:

[host1]
ip_address=192.168.122.3
root_login='root'
root_password='password'
[host2]
ip_address=192.168.2.109
root_login='root'
root_password='password'


## Системные требования к окружению

Необходимо создать каталог /pgpro на диске. В данном каталоге будут хранится виртуальные машины используемые для запуска тестов.
- пакеты для RPM-based дистрибутивов:
```
yum install -y git libvirt libvirt-python qemu-kvm gcc openssl-devel python-devel python-cffi vim samba
```
Версия пакета libvirt должна быть не ниже 2.0.

## Рекомендации для тестов:

- http://www.sqlstyle.guide/

## Настройка сервера для запуска тестов:

- пакеты для RPM-based дистрибутивов:
```
yum install -y git libvirt libvirt-python qemu-kvm gcc openssl-devel python-devel python-cffi vim samba
```
- установить PyPA:
```
curl -O https://bootstrap.pypa.io/get-pip.py
python get-pip.py
```
- установить зависимости для [Ansible](https://www.ansible.com/) (см. также
[инструкцию](http://docs.ansible.com/ansible/intro_installation.html)):
```
	Debian-based: apt install -y libssl-dev gcc
	RPM-based: yum install -y openssl-devel gcc
```
- установить Ansible и модули для него: ```sudo pip install ansible pywinrm paramiko```
- если для запуска ВМ скрипт не найдет шаблон ВМ, то он его загрузит, но можно
заранее загрузить все шаблоны виртуальных машин. Например так: ```wget -np -nd
-A qcow2 -r -l 1 http://webdav.l.postgrespro.ru/DIST/vm-images/test/```
- для доступа по SSH ключам в гостевые ОС нужно скопировать ключи из репозитория:
```
	cp static/id_rsa ~/.ssh/id_rsa.pg-tests
	cat static/authorized_keys >> ~/.ssh/authorized_keys
	chmod 700 ~/.ssh/id_rsa.pg-tests
```
и добавить их вместе с полезными опциями в конфиг ~/.ssh/config:
```
	Compression yes
	CompressionLevel 9
	HashKnownHosts yes
	ServerAliveInterval 120
	TCPKeepAlive no

	Host *
        User							test
        UseRoaming=no
        IdentityFile                    ~/.ssh/id_rsa.pg-tests
```

### Настройки ОС для тестирования

Все необходимые настройки выполняются сценарием для Ansible в tests/playbook-prepare-env.yml,
который запускается скриптом testrun.py перед запуском теста. Но можно запустить и вручную:
```
$ cat static/inventory
ubuntu1604 ansible_host=127.0.0.1 ansible_become_pass=TestRoot1 ansible_ssh_pass=TestPass1 ansible_user=test ansible_become_user=root
$ ansible-playbook tests/playbook-prepare-env.yml -i static/inventory -c paramiko --limit ubuntu1604
$ ansible ubuntu1604 -m setup -i static/inventory -c paramiko
```
