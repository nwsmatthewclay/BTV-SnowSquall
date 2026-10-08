const CONFIG = {
  repository: 'nwsmatthewclay/BTV-SnowSquall',
  eventType: 'kcxx_scan',
  githubTokenProperty: 'GITHUB_TOKEN',
  topicArn: 'arn:aws:sns:us-east-1:684042711724:NewNEXRADLevel2ObjectFilterable',
  radar: 'KCXX',
  historyProperty: 'DISPATCHED_KCXX_VOLUMES',
  maxHistory: 100,
};

/**
 * AWS SNS HTTPS endpoint for NOAA NEXRAD Level-II notifications.
 * Deploy as a web app accessible by anyone, then use its URL as the SNS
 * subscription endpoint. The first SNS SubscriptionConfirmation is accepted
 * automatically. Notification messages are filtered to KCXX and de-duplicated
 * by radar date/time/volume before GitHub is dispatched.
 */
function doPost(e) {
  try {
    const envelope = JSON.parse((e && e.postData && e.postData.contents) || '{}');

    if (envelope.Type === 'SubscriptionConfirmation') {
      if (envelope.TopicArn !== CONFIG.topicArn) {
        return jsonResponse({ok: false, error: 'Unexpected SNS topic'});
      }
      const url = envelope.SubscribeURL;
      if (!url) return jsonResponse({ok: false, error: 'Missing SubscribeURL'});
      UrlFetchApp.fetch(url, {method: 'get', muteHttpExceptions: true});
      return jsonResponse({ok: true, action: 'subscription_confirmed'});
    }

    if (envelope.Type !== 'Notification') {
      return jsonResponse({ok: true, action: 'ignored_type'});
    }
    if (envelope.TopicArn !== CONFIG.topicArn) {
      return jsonResponse({ok: false, error: 'Unexpected SNS topic'});
    }

    const message = typeof envelope.Message === 'string'
      ? JSON.parse(envelope.Message)
      : envelope.Message;

    if (!message || message.SiteID !== CONFIG.radar || !message.DateTime || !message.VolumeID) {
      return jsonResponse({ok: true, action: 'ignored_site'});
    }

    const key = [message.SiteID, message.DateTime, message.VolumeID].join('|');
    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    try {
      const seen = loadHistory();
      if (seen.indexOf(key) !== -1) {
        return jsonResponse({ok: true, action: 'duplicate', key: key});
      }

      const token = PropertiesService.getScriptProperties().getProperty(CONFIG.githubTokenProperty);
      if (!token) throw new Error('Missing Script Property GITHUB_TOKEN');

      const payload = {
        event_type: CONFIG.eventType,
        client_payload: {
          radar: message.SiteID,
          scan_time: normalizeUtc(message.DateTime),
          volume_id: String(message.VolumeID),
          chunk_id: message.ChunkID ? String(message.ChunkID) : null,
          chunk_type: message.ChunkType || null,
          source: 'NOAA_NEXRAD_AWS_SNS',
        },
      };

      const response = UrlFetchApp.fetch(
        'https://api.github.com/repos/' + CONFIG.repository + '/dispatches',
        {
          method: 'post',
          contentType: 'application/json',
          headers: {
            Authorization: 'Bearer ' + token,
            Accept: 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
          },
          payload: JSON.stringify(payload),
          muteHttpExceptions: true,
        }
      );

      const status = response.getResponseCode();
      if (status < 200 || status >= 300) {
        throw new Error('GitHub dispatch failed: HTTP ' + status + ' ' + response.getContentText());
      }

      seen.push(key);
      while (seen.length > CONFIG.maxHistory) seen.shift();
      saveHistory(seen);
      return jsonResponse({ok: true, action: 'dispatched', key: key, scan_time: payload.client_payload.scan_time});
    } finally {
      lock.releaseLock();
    }
  } catch (err) {
    console.error(err);
    return jsonResponse({ok: false, error: String(err)});
  }
}

function normalizeUtc(value) {
  const text = String(value).trim();
  if (/Z$/.test(text)) return text;
  return text + 'Z';
}

function loadHistory() {
  const raw = PropertiesService.getScriptProperties().getProperty(CONFIG.historyProperty);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (err) {
    return [];
  }
}

function saveHistory(values) {
  PropertiesService.getScriptProperties().setProperty(CONFIG.historyProperty, JSON.stringify(values));
}

function jsonResponse(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

function healthCheck() {
  return jsonResponse({ok: true, service: 'BTV-SnowSquall NEXRAD SNS bridge'});
}
