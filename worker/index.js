// Telegram webhook for @intsystems_media_bot: preview buttons and editor replies.
// State lives in posts/*.md; every action is a commit through the GitHub API.
// Commits carry [skip ci] so they do not trigger previews; header edits and
// "publish now" dispatch the workflows explicitly.

const PROMPTS = {
  t: "✏️ New caption for",
  h: "🖼 New header for",
  d: "📅 New date for",
};
const HINTS = {
  t: "Reply with the text; formatting and links are kept.",
  h: "Reply with the title on the first line and an optional subtitle on the second.",
  d: "Reply with YYYY-MM-DD HH:MM, Moscow time.",
};
const CAPTION_LIMIT = 1024;
const REEL_HELP = [
  "/reel, then a scenario in TOML (reels/example.toml in the repo):",
  "",
  'background = "black-design-2"',
  'accent = "#1ED760"',
  'caption = "<b>Post text</b> for the channel, optional"',
  "",
  "[[frame]]",
  'kind = "title"',
  'badge = "Статья"',
  'title = "Сколько данных нужно модели?"',
  "duration = 3.5",
  "",
  "[[frame]]",
  'kind = "outro"',
  'cta = "Подробнее в Telegram-канале кафедры"',
  "",
  "Frame kinds: title, text, formula, image, person, outro.",
].join("\n");

export default {
  async fetch(request, env, ctx) {
    if (request.method !== "POST" || request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    const update = await request.json();
    ctx.waitUntil(
      handle(update, env).catch((error) => tg(env, "sendMessage", { chat_id: env.EDITOR_ID, text: `⚠️ ${error.message}` })),
    );
    return new Response("ok");
  },
};

async function handle(update, env) {
  if (update.callback_query) return onButton(update.callback_query, env);
  const message = update.message;
  if (!message || String(message.from?.id) !== env.EDITOR_ID) return;
  const prompt = message.reply_to_message?.text ?? "";
  const kind = Object.keys(PROMPTS).find((key) => prompt.startsWith(PROMPTS[key]));
  if (!kind) return onPost(message, env);
  const path = prompt.match(/posts\/\S+\.md/)[0];
  const photoId = Number(prompt.match(/#(\d+)/)[1]);
  return onReply(kind, path, photoId, message, env);
}

// Any other message is a post the editor wrote: the text is kept, the Action makes the header.
async function onPost(message, env) {
  const text = message.text ?? message.caption ?? "";
  const reply = (body) => tg(env, "sendMessage", { chat_id: env.EDITOR_ID, text: body, reply_parameters: { message_id: message.message_id } });
  if (text.startsWith("/reel")) {
    const scenario = text.replace(/^\/reel(@\w+)?/, "").trim();
    if (!scenario) return reply(REEL_HELP);
    await dispatch(env, "reel.yml", { scenario });
    return reply("🎬 Rendering the reel, the video comes in about 3 min.");
  }
  if (text.startsWith("/cover")) {
    await dispatch(env, "cover.yml", { text: text.replace(/^\/cover(@\w+)?/, "").trim() });
    return reply("🖼 Rendering the header, the file comes in about 2 min.");
  }
  if (!text || text.startsWith("/")) {
    return tg(env, "sendMessage", {
      chat_id: env.EDITOR_ID,
      text: [
        "Send a post as it should appear in the channel: the bot makes the header and sends a preview in about 3 min.",
        "",
        "Header only, as a PNG file:",
        "/cover",
        "Title",
        "Subtitle or -",
        "person id and rubric, optional (paper, accepted, award, event, seminar, deadlines, news)",
        "",
        "Reel: /reel with a scenario; send /reel alone for an example.",
      ].join("\n"),
    });
  }
  if (text.length > CAPTION_LIMIT) return reply(`Too long: ${text.length}/${CAPTION_LIMIT}.`);
  await dispatch(env, "draft-post.yml", { caption: toHtml(text, message.entities ?? message.caption_entities) });
  return reply("🖼 Making the header, the preview comes in about 3 min.");
}

async function onButton(query, env) {
  if (String(query.from.id) !== env.EDITOR_ID) {
    return tg(env, "answerCallbackQuery", { callback_query_id: query.id, text: "Only the editor can do this." });
  }
  await tg(env, "answerCallbackQuery", { callback_query_id: query.id });
  const [action, stem] = query.data.split(/:(.*)/s);
  const path = `posts/${stem}.md`;
  const card = query.message;
  const photoId = card.reply_to_message?.message_id;

  // Reel cards: the video is the message the card replies to; copying it posts it with its caption.
  if (action === "v" || action === "x") {
    let note = "❌ Discarded";
    if (action === "v") {
      const copy = await tg(env, "copyMessage", { chat_id: env.CHANNEL_ID, from_chat_id: card.chat.id, message_id: photoId });
      note = `📤 Posted to the channel, message ${copy.message_id}`;
    }
    return tg(env, "editMessageText", { chat_id: card.chat.id, message_id: card.message_id, text: `${card.text}\n${note}` });
  }

  if (action in PROMPTS) {
    return tg(env, "sendMessage", {
      chat_id: env.EDITOR_ID,
      text: `${PROMPTS[action]} ${path} #${photoId}\n${HINTS[action]}`,
      reply_markup: { force_reply: true },
    });
  }
  const file = await readFile(env, path);
  if (getMeta(file.text, "status") === "published") {
    return tg(env, "sendMessage", { chat_id: env.EDITOR_ID, text: `${path} is already published.` });
  }
  let text = file.text;
  let note;
  if (action === "p") {
    text = setMeta(setMeta(text, "status", "approved"), "date", moscowNow());
    note = "✅ Publishing now, about 2 min";
  } else if (action === "s") {
    text = setMeta(text, "status", "approved");
    note = `🕒 Scheduled for ${getMeta(text, "date")}`;
  } else if (action === "r") {
    text = setMeta(text, "status", "rejected");
    note = "❌ Rejected";
  } else {
    return;
  }
  await writeFile(env, path, text, file.sha, `chore: ${note.slice(2).toLowerCase()} ${path} [skip ci]`);
  if (action === "p") await dispatch(env, "publish-posts.yml", {});
  return tg(env, "editMessageText", { chat_id: card.chat.id, message_id: card.message_id, text: `${card.text}\n${note}` });
}

async function onReply(kind, path, photoId, message, env) {
  const file = await readFile(env, path);
  let text = file.text;
  const reply = (body) => tg(env, "sendMessage", { chat_id: env.EDITOR_ID, text: body, reply_parameters: { message_id: message.message_id } });

  if (kind === "t") {
    // JS string length is in UTF-16 code units, as Telegram counts.
    if (message.text.length > CAPTION_LIMIT) return reply(`Too long: ${message.text.length}/${CAPTION_LIMIT}.`);
    const caption = toHtml(message.text, message.entities);
    text = text.replace(/\n---\n[\s\S]*$/, `\n---\n${caption}\n`);
    await writeFile(env, path, text, file.sha, `chore: edit caption of ${path} [skip ci]`);
    await tg(env, "editMessageCaption", { chat_id: env.EDITOR_ID, message_id: photoId, caption, parse_mode: "HTML" });
    return reply("✅ Caption updated.");
  }
  if (kind === "h") {
    const [title, subtitle] = message.text.split("\n").map((line) => tex(line.trim()));
    text = setMeta(text, "title", title);
    text = subtitle ? setMeta(text, "subtitle", subtitle) : text.replace(/^subtitle:.*\n/m, "");
    await writeFile(env, path, text, file.sha, `chore: edit header of ${path} [skip ci]`);
    await dispatch(env, "preview-posts.yml", { post: path });
    return reply("🖼 Re-rendering, a new preview comes in about 2 min.");
  }
  if (kind === "d") {
    const date = message.text.trim();
    if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(date)) return reply("Expected YYYY-MM-DD HH:MM.");
    await writeFile(env, path, setMeta(text, "date", date), file.sha, `chore: set date of ${path} [skip ci]`);
    return reply(`📅 Date set to ${date}. Press 🕒 to schedule.`);
  }
}

// --- posts ------------------------------------------------------------------

function getMeta(text, key) {
  return text.match(new RegExp(`^${key}: (.*)$`, "m"))?.[1];
}

// Same rule as set_meta in scripts/send_post.py: replace the line or add it before the closing ---.
function setMeta(text, key, value) {
  const [head, body] = text.split(/\n---\n([\s\S]*)/);
  const line = `${key}: ${value}`;
  const re = new RegExp(`^${key}:.*$`, "m");
  return `${re.test(head) ? head.replace(re, line) : `${head}\n${line}`}\n---\n${body}`;
}

function moscowNow() {
  return new Date(Date.now() + 3 * 3600e3).toISOString().slice(0, 16).replace("T", " ");
}

// Header fields are TeX: escape specials the editor types as plain text.
function tex(line) {
  return line.replace(/(?<!\\)([%&#$_])/g, "\\$1");
}

const escapeHtml = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const TAGS = {
  bold: ["<b>", "</b>"],
  italic: ["<i>", "</i>"],
  underline: ["<u>", "</u>"],
  strikethrough: ["<s>", "</s>"],
  spoiler: ["<tg-spoiler>", "</tg-spoiler>"],
  code: ["<code>", "</code>"],
  pre: ["<pre>", "</pre>"],
  blockquote: ["<blockquote>", "</blockquote>"],
  expandable_blockquote: ["<blockquote expandable>", "</blockquote>"],
};

// Telegram entities (UTF-16 offsets, like JS strings) to Telegram HTML.
function toHtml(text, entities = []) {
  const opens = {};
  const closes = {};
  const sorted = [...entities].sort((a, b) => a.offset - b.offset || b.length - a.length);
  for (const entity of sorted) {
    const pair = entity.type === "text_link" ? [`<a href="${escapeHtml(entity.url)}">`, "</a>"] : TAGS[entity.type];
    if (!pair) continue;
    (opens[entity.offset] ??= []).push(pair[0]);
    (closes[entity.offset + entity.length] ??= []).unshift(pair[1]);
  }
  let html = "";
  for (let i = 0; i <= text.length; i++) {
    html += (closes[i] ?? []).join("") + (opens[i] ?? []).join("");
    if (i < text.length) html += escapeHtml(text[i]);
  }
  return html;
}

// --- APIs -------------------------------------------------------------------

async function tg(env, method, body) {
  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!result.ok) throw new Error(`${method}: ${result.description}`);
  return result.result;
}

async function github(env, path, init = {}) {
  const response = await fetch(`https://api.github.com/repos/${env.REPO}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "intsystems-media-bot",
    },
  });
  if (!response.ok) throw new Error(`GitHub ${path}: ${response.status} ${await response.text()}`);
  return response.status === 204 ? null : response.json();
}

async function readFile(env, path) {
  const file = await github(env, `/contents/${path}?ref=main`);
  const bytes = Uint8Array.from(atob(file.content.replace(/\n/g, "")), (c) => c.charCodeAt(0));
  return { text: new TextDecoder().decode(bytes), sha: file.sha };
}

async function writeFile(env, path, text, sha, message) {
  let binary = "";
  for (const byte of new TextEncoder().encode(text)) binary += String.fromCharCode(byte);
  await github(env, `/contents/${path}`, {
    method: "PUT",
    body: JSON.stringify({ message, content: btoa(binary), sha, branch: "main" }),
  });
}

function dispatch(env, workflow, inputs) {
  return github(env, `/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    body: JSON.stringify({ ref: "main", inputs }),
  });
}
