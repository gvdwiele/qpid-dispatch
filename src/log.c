/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

#include "log_private.h"
#include <qpid/dispatch/ctools.h>
#include <qpid/dispatch/alloc.h>
#include <qpid/dispatch/threading.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#define TEXT_MAX 512
#define LIST_MAX 1000

typedef struct qd_log_entry_t qd_log_entry_t;

struct qd_log_entry_t {
    DEQ_LINKS(qd_log_entry_t);
    const char     *module;
    int             cls;
    const char     *file;
    int             line;
    time_t          time;
    char            text[TEXT_MAX];
};

ALLOC_DECLARE(qd_log_entry_t);
ALLOC_DEFINE(qd_log_entry_t);

DEQ_DECLARE(qd_log_entry_t, qd_log_list_t);

static int            mask = LOG_INFO;
static qd_log_list_t  entries;
static sys_mutex_t   *log_lock = 0;


static const char *cls_prefix(int cls)
{
    switch (cls) {
    case LOG_TRACE    : return "TRACE";
    case LOG_DEBUG    : return "DEBUG";
    case LOG_INFO     : return "INFO";
    case LOG_NOTICE   : return "NOTICE";
    case LOG_WARNING  : return "WARNING";
    case LOG_ERROR    : return "ERROR";
    case LOG_CRITICAL : return "CRITICAL";
    }

    return "";
}

void qd_log_impl(const char *module, int cls, const char *file, int line, const char *fmt, ...)
{
    if (!(cls & mask))
        return;

    qd_log_entry_t *entry = new_qd_log_entry_t();
    DEQ_ITEM_INIT(entry);
    entry->module = module;
    entry->cls    = cls;
    entry->file   = file;
    entry->line   = line;
    time(&entry->time);

    char ctime[100];
    va_list ap;

    va_start(ap, fmt);
    vsnprintf(entry->text, TEXT_MAX, fmt, ap);
    va_end(ap);
    ctime_r(&entry->time, ctime);
    ctime[24] = '\0';
    fprintf(stderr, "%s %s (%s) %s\n", ctime, module, cls_prefix(cls), entry->text);

    sys_mutex_lock(log_lock);
    DEQ_INSERT_TAIL(entries, entry);
    if (DEQ_SIZE(entries) > LIST_MAX) {
        entry = DEQ_HEAD(entries);
        DEQ_REMOVE_HEAD(entries);
        free_qd_log_entry_t(entry);
    }
    sys_mutex_unlock(log_lock);
}

void qd_log_set_mask(int _mask)
{
    mask = _mask;
}


void qd_log_initialize(void)
{
    DEQ_INIT(entries);
    log_lock = sys_mutex();
}


void qd_log_finalize(void)
{
}


