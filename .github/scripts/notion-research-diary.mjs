/**
 * Purpose
 * -------
 * Record GitHub push or manually selected commits in a Notion Research Diary with
 * canonical-link idempotency.
 *
 * Inputs
 * ------
 * Actions event JSON and environment settings
 *     Runtime configuration and injectable HTTP/timer/log dependencies are handled by
 *     run().
 *
 * Outputs
 * -------
 * Exported testable helpers and an optional command-line execution path
 *     Direct execution may query GitHub/Notion and create diary pages; importing the
 *     module alone performs no publication.
 */
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { fileURLToPath } from "node:url";

// Current stable API versions, verified against the vendors' documentation.
export const NOTION_VERSION = "2026-03-11";
const GITHUB_API_VERSION = "2026-03-10";
const COMMIT_LINK = "Commit Link";
const FULL_SHA = /^[0-9a-f]{40}$/i;

/**
 * Purpose
 * -------
 * Require a nonblank configuration value before a request or event operation.
 *
 * Inputs
 * ------
 * env: object
 *     Environment mapping supplying the named value.
 * name: string
 *     Required environment-key name.
 *
 * Outputs
 * -------
 * value: string
 *     Trimmed configuration value; missing/blank values throw Error.
 */
function required(env, name) {
  if (!env[name]?.trim()) {
    throw new Error(`Missing ${name}. Configure the repository secret or Actions environment.`);
  }
  return env[name].trim();
}

/**
 * Purpose
 * -------
 * Redact configured sensitive values and emit one prefixed log line.
 *
 * Inputs
 * ------
 * message: unknown
 *     Message converted to text before redaction.
 * env: object
 *     Environment containing token/data-source/owner values to redact when set.
 * output: function, optional
 *     Log sink receiving the sanitized line; defaults to console.log.
 *
 * Outputs
 * -------
 * undefined
 *     Writes one line with CR/LF escaped so API text cannot introduce new Actions
 *     command lines.
 */
export function safeLog(message, env, output = console.log) {
  let text = String(message);
  // Remove configured credentials and identifiers before formatting log text
  for (const name of ["NOTION_TOKEN", "GITHUB_TOKEN", "NOTION_DATA_SOURCE_ID", "NOTION_OWNER_USER_ID"]) {
    const value = env[name]?.trim();
    if (value) text = text.replaceAll(value, "[REDACTED]");
  }
  // Keep untrusted API responses on one prefixed line, away from Actions commands.
  output(`[research-diary] ${text.replaceAll("\r", "\\r").replaceAll("\n", "\\n")}`);
}

/**
 * Purpose
 * -------
 * Issue a bounded HTTP JSON request with explicit rate-limit retry handling.
 *
 * Inputs
 * ------
 * url: string
 *     Exact endpoint URL.
 * options: object
 *     Fetch method, headers, and optional serialized body.
 * fetchImpl: function
 *     Injected fetch-compatible implementation.
 * wait: function
 *     Injected async delay accepting milliseconds.
 * log: function
 *     Sanitized logging callback used for rate-limit messages.
 *
 * Outputs
 * -------
 * result: Promise<unknown>
 *     Parsed successful JSON. HTTP/transport/JSON failures reject; only supported 429
 *     responses are retried, at most three times.
 */
async function requestJson(url, options, { fetchImpl, wait, log }) {
  for (let attempt = 0; ; attempt += 1) {
    let response;
    let text;
    try {
      response = await fetchImpl(url, {
        ...options,
        redirect: "error",
        signal: AbortSignal.timeout(30_000),
      });
      text = await response.text();
    } catch (error) {
      // A failed page-create request might already have succeeded server-side.
      // Never blindly retry an ambiguous write; a rerun checks Commit Link first.
      throw new Error(`${options.method} ${url} failed: ${error.message}`);
    }

    // Retry only an explicit bounded rate-limit response with a usable delay
    if (response.status === 429 && attempt < 3) {
      const seconds = Number(response.headers.get("retry-after") ?? 1);
      if (Number.isFinite(seconds) && seconds >= 0 && seconds <= 60) {
        log(`HTTP 429 from ${url}; retrying after ${seconds}s (${attempt + 1}/3).`);
        await wait(Math.max(1, seconds) * 1000);
        continue;
      }
    }
    // Surface HTTP details before accepting and parsing a successful JSON body
    if (!response.ok) {
      throw new Error(`${options.method} ${url}: HTTP ${response.status}; ${text}`);
    }
    try {
      return JSON.parse(text);
    } catch {
      throw new Error(`${options.method} ${url}: HTTP ${response.status}; invalid JSON response.`);
    }
  }
}

/**
 * Purpose
 * -------
 * Validate complete commit metadata and construct its canonical permanent repository
 * URL.
 *
 * Inputs
 * ------
 * sha: string
 *     Full forty-character hexadecimal commit SHA.
 * message: string
 *     Complete original commit message.
 * repositoryUrl: string
 *     Canonical repository web URL without a trailing commit path.
 *
 * Outputs
 * -------
 * commit: object
 *     Lowercase sha, unchanged message, and canonical commit url; malformed metadata
 *     throws Error.
 */
function normalizeCommit(sha, message, repositoryUrl) {
  if (typeof sha !== "string" || !FULL_SHA.test(sha)) {
    throw new Error("Commit metadata must contain a full 40-character commit SHA.");
  }
  if (typeof message !== "string") {
    throw new Error(`Commit ${sha} has no valid commit message.`);
  }
  return {
    sha: sha.toLowerCase(),
    message,
    url: `${repositoryUrl}/commit/${sha.toLowerCase()}`,
  };
}

/**
 * Purpose
 * -------
 * Read repository-scoped GitHub metadata using the configured token and pinned API
 * version.
 *
 * Inputs
 * ------
 * path: string
 *     Repository-relative API path including its leading slash.
 * env: object
 *     Repository/API/token environment values.
 * http: object
 *     Injected fetchImpl, wait, and sanitized log dependencies.
 *
 * Outputs
 * -------
 * response: Promise<unknown>
 *     Parsed GitHub GET response; request/configuration errors reject.
 */
async function githubRequest(path, env, http) {
  const apiUrl = (env.GITHUB_API_URL ?? "https://api.github.com").replace(/\/$/, "");
  return requestJson(`${apiUrl}/repos/${env.GITHUB_REPOSITORY}${path}`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${required(env, "GITHUB_TOKEN")}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": GITHUB_API_VERSION,
    },
  }, http);
}

/**
 * Purpose
 * -------
 * Select every push commit or resolve one explicitly selected manual commit.
 *
 * Inputs
 * ------
 * event: object
 *     Parsed Actions push or workflow_dispatch event.
 * env: object
 *     Event name, repository, selected HEAD SHA/ref, and GitHub request settings.
 * repositoryUrl: string
 *     Canonical repository web URL for permanent commit links.
 * http: object
 *     Injected HTTP dependencies.
 * log: function
 *     Sanitized run-progress logger.
 *
 * Outputs
 * -------
 * commits: Promise<Array<object>>
 *     Normalized complete push collection or one GitHub-resolved manual commit. Invalid
 *     payloads, ambiguous/mismatched metadata, or request failures reject.
 */
async function selectCommits(event, env, repositoryUrl, http, log) {
  if (env.GITHUB_EVENT_NAME === "push") {
    const commits = event.commits ?? [];
    if (!Array.isArray(commits)) throw new Error("push.commits must be an array.");
    // Process the complete collection, including commits already seen on another branch.
    return commits.map(({ id, message }) => normalizeCommit(id, message, repositoryUrl));
  }

  // Resolve manual abbreviations against GitHub instead of trusting event commit metadata
  const input = event.inputs?.commit_sha ?? "";
  if (typeof input !== "string") throw new Error("commit_sha must be a string.");
  const selectedSha = input.trim() || required(env, "GITHUB_SHA");
  if (!/^[0-9a-f]{7,40}$/i.test(selectedSha)) {
    throw new Error(`Cannot resolve manual commit_sha ${JSON.stringify(selectedSha)}: use a full SHA or an unambiguous 7–40 character hexadecimal abbreviation.`);
  }
  log(`Manual-test mode: resolving ${selectedSha}${input.trim() ? " (commit_sha input)" : ` (HEAD selected for ${env.GITHUB_REF ?? "this run"})`}.`);
  let commit;
  try {
    commit = await githubRequest(`/commits/${encodeURIComponent(selectedSha)}`, env, http);
  } catch (error) {
    throw new Error(`Cannot resolve manual commit ${selectedSha}: ${error.message}`);
  }
  if (typeof commit.sha !== "string" || !commit.sha.toLowerCase().startsWith(selectedSha.toLowerCase())) {
    throw new Error(`GitHub returned a different SHA for manual commit ${selectedSha}.`);
  }
  return [normalizeCommit(commit.sha, commit.commit?.message, repositoryUrl)];
}

/**
 * Purpose
 * -------
 * Locate the sole native title property in a Notion data-source schema.
 *
 * Inputs
 * ------
 * schema: object
 *     Data-source schema with named properties.
 * label: string
 *     Human-readable data-source label used in validation errors.
 *
 * Outputs
 * -------
 * name: string
 *     Unique title-property name; zero or multiple title properties throw Error.
 */
function titleProperty(schema, label) {
  const titles = Object.entries(schema.properties ?? {}).filter(([, property]) => property.type === "title");
  if (titles.length !== 1) throw new Error(`${label} must have exactly one title property.`);
  return titles[0][0];
}

/**
 * Purpose
 * -------
 * Resolve one exact repository project using its literal or readable Notion title.
 *
 * Inputs
 * ------
 * notion: function
 *     Injected authenticated Notion request adapter.
 * projectDataSourceId: string
 *     Related Project data-source identifier.
 * repositoryName: string
 *     Repository basename used for literal then underscore/hyphen-to-space matching.
 * log: function
 *     Sanitized resolution logger.
 *
 * Outputs
 * -------
 * projectId: Promise<string>
 *     Unique matching project page ID. Missing/ambiguous or inconsistent query results
 *     reject before diary creation.
 */
async function resolveProject(notion, projectDataSourceId, repositoryName, log) {
  const schema = await notion(`/data_sources/${encodeURIComponent(projectDataSourceId)}`);
  const property = titleProperty(schema, "Project data source");
  // Prefer the literal repository name, then its readable space-separated spelling.
  const candidates = new Set([repositoryName, repositoryName.replace(/[_-]+/g, " ")]);
  for (const name of candidates) {
    const result = await notion(`/data_sources/${encodeURIComponent(projectDataSourceId)}/query`, {
      filter: { property, title: { equals: name } },
      page_size: 2,
    });
    if (!Array.isArray(result.results)) throw new Error("Invalid Notion project-query response.");
    if (result.results.length > 1 || result.has_more) {
      throw new Error(`Multiple Notion projects match ${JSON.stringify(name)}; project names must be unique.`);
    }
    if (result.results.length === 1) {
      const project = result.results[0];
      const actualName = (project.properties?.[property]?.title ?? [])
        .map((part) => part.plain_text ?? part.text?.content ?? "").join("");
      if (!project.id || actualName.toLowerCase() !== name.toLowerCase()) {
        throw new Error("Notion returned a project without a matching name and page ID.");
      }
      log(`Resolved project: ${JSON.stringify(actualName)}.`);
      return project.id;
    }
  }
  throw new Error(`No Notion project matches repository ${JSON.stringify(repositoryName)}. Share the Project data source with the integration and check its project titles.`);
}

/**
 * Purpose
 * -------
 * Resolve one native Notion person using an explicit UUID or verified display-name
 * lookup.
 *
 * Inputs
 * ------
 * notion: function
 *     Injected authenticated Notion request adapter.
 * env: object
 *     Optional NOTION_OWNER_USER_ID override.
 * log: function
 *     Sanitized owner-resolution logger.
 *
 * Outputs
 * -------
 * ownerId: Promise<string>
 *     Verified native person ID; malformed UUIDs, bots, ambiguous/missing matches, or
 *     invalid pagination reject.
 */
async function resolveOwner(notion, env, log) {
  const configuredId = env.NOTION_OWNER_USER_ID?.trim();
  if (configuredId) {
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(configuredId)) {
      throw new Error("NOTION_OWNER_USER_ID must be a native Notion user UUID.");
    }
    const user = await notion(`/users/${encodeURIComponent(configuredId)}`);
    if (user.type !== "person" || user.id !== configuredId) {
      throw new Error("NOTION_OWNER_USER_ID must resolve to a person, not an integration bot.");
    }
    log(`Resolved owner: ${JSON.stringify(user.name)} (native Notion person).`);
    return user.id;
  }

  // Search every user page and require one native person with the verified normalized name
  const matches = [];
  const cursors = new Set();
  let cursor;
  do {
    const query = new URLSearchParams({ page_size: "100" });
    if (cursor) query.set("start_cursor", cursor);
    const result = await notion(`/users?${query}`);
    if (!Array.isArray(result.results)) throw new Error("Invalid Notion users response.");
    for (const user of result.results) {
      const name = (user.name ?? "").replaceAll(".", "").replace(/\s+/g, " ").trim().toLowerCase();
      if (user.type === "person" && ["julio m morales", "julio morales"].includes(name)) matches.push(user);
    }
    if (!result.has_more) break;
    cursor = result.next_cursor;
    if (!cursor || cursors.has(cursor)) throw new Error("Invalid Notion user pagination cursor.");
    cursors.add(cursor);
  } while (true);
  if (matches.length !== 1 || !matches[0].id) {
    throw new Error("Expected one Notion person named Julio M. Morales or Julio Morales. Configure NOTION_OWNER_USER_ID to select the verified account explicitly.");
  }
  log(`Resolved owner: ${JSON.stringify(matches[0].name)} (native Notion person).`);
  return matches[0].id;
}

// Shared by push and workflow_dispatch. Commit Link is the sole idempotency key.
/**
 * Purpose
 * -------
 * Create one diary page only when its canonical Commit Link has not already been
 * recorded.
 *
 * Inputs
 * ------
 * sha, message, url: strings
 *     Normalized full SHA, complete message, and canonical commit URL.
 * notion: function
 *     Authenticated query/page-create adapter.
 * dataSourceId: string
 *     Research Diary data source receiving the page.
 * titleProperty: string
 *     Validated native title-property name.
 * getPageProperties: function
 *     Lazy async project/owner enrichment provider.
 * log: function
 *     Sanitized run-progress logger.
 * seen: Set<string>
 *     Canonical commit URLs already confirmed within this run, updated in place.
 *
 * Outputs
 * -------
 * status: Promise<string>
 *     created or skipped. Creation uses only the message subject as chunked rich text.
 *     Query/write validation failures reject, including ambiguous create responses.
 */
export async function processCommit({ sha, message, url }, { notion, dataSourceId, titleProperty, getPageProperties, log, seen }) {
  log(`Processing commit ${sha}: ${url}`);
  if (seen.has(url)) {
    log(`Skipped existing commit ${sha} (already processed in this run).`);
    return "skipped";
  }
  // Query the canonical permanent URL before requesting enrichment or creating a page
  const existing = await notion(`/data_sources/${encodeURIComponent(dataSourceId)}/query`, {
    filter: { property: COMMIT_LINK, url: { equals: url } },
    page_size: 1,
  });
  if (!Array.isArray(existing.results)) throw new Error(`Invalid Notion duplicate-query response for ${sha}.`);
  if (existing.results.length > 0) {
    seen.add(url);
    log(`Skipped existing commit ${sha} (matching Commit Link).`);
    return "skipped";
  }

  // Preserve the complete subject while keeping each Unicode-rich text chunk within API limits
  const subject = message.split(/\r\n|\n|\r/, 1)[0];
  // 1000 code points fit within 2000 UTF-16 units, including emoji, without splitting them.
  const title = (subject.match(/[\s\S]{1,1000}/gu) ?? []).map((content) => ({
    type: "text",
    text: { content },
  }));
  // Create one page with explicit native title, URL, project, and people properties
  const page = await notion("/pages", {
    parent: { type: "data_source_id", data_source_id: dataSourceId },
    properties: {
      [titleProperty]: { title },
      [COMMIT_LINK]: { url },
      ...await getPageProperties(),
    },
  });
  if (page.object !== "page" || !page.id) throw new Error(`Invalid Notion page-create response for ${sha}; rerun to check whether it was recorded.`);
  seen.add(url);
  log(`Created Research Diary page for commit ${sha}.`);
  return "created";
}

/**
 * Purpose
 * -------
 * Validate an Actions event and record its selected commits with shared duplicate
 * protection and lazy enrichment.
 *
 * Inputs
 * ------
 * env: object, optional
 *     Actions/Notion configuration; defaults to process.env.
 * fetchImpl: function, optional
 *     Fetch implementation; defaults to globalThis.fetch for normal execution.
 * wait: function, optional
 *     Millisecond-delay provider; defaults to the native promise timer.
 * output: function, optional
 *     Output sink passed through safeLog.
 *
 * Outputs
 * -------
 * counts: Promise<object>
 *     Created/skipped counts. Deletion/empty pushes return zero counts without Notion
 *     access; unsupported events, invalid configuration/schema, or per-commit failures
 *     reject.
 */
export async function run({ env = process.env, fetchImpl = globalThis.fetch, wait = sleep, output = console.log } = {}) {
  /**
   * Purpose
   * -------
   * Bind the current environment and output sink to the sanitized run logger.
   *
   * Inputs
   * ------
   * message: unknown
   *     Progress or API error text to redact and prefix.
   *
   * Outputs
   * -------
   * undefined
   *     Emits one safe line through the enclosing output dependency.
   */
  const log = (message) => safeLog(message, env, output);
  const eventName = required(env, "GITHUB_EVENT_NAME");
  log(`Execution source: ${eventName}${eventName === "workflow_dispatch" ? " (manual-test mode)" : ""}.`);
  if (!["push", "workflow_dispatch"].includes(eventName)) {
    throw new Error(`Unsupported event: ${eventName}.`);
  }
  const event = JSON.parse(await readFile(required(env, "GITHUB_EVENT_PATH"), "utf8"));
  if (eventName === "push" && event.deleted) {
    log("Ignored deletion push; no commits to record.");
    return { created: 0, skipped: 0 };
  }
  const repository = required(env, "GITHUB_REPOSITORY");
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)) {
    throw new Error("GITHUB_REPOSITORY must be owner/repository.");
  }
  const repositoryUrl = `${(env.GITHUB_SERVER_URL ?? "https://github.com").replace(/\/$/, "")}/${repository}`;
  const http = { fetchImpl, wait, log };
  const commits = await selectCommits(event, env, repositoryUrl, http, log);
  if (commits.length === 0) {
    log("Push contains zero commits; nothing to record.");
    return { created: 0, skipped: 0 };
  }

  const token = required(env, "NOTION_TOKEN");
  const dataSourceId = required(env, "NOTION_DATA_SOURCE_ID");
  /**
   * Purpose
   * -------
   * Bind the authenticated Notion endpoint and native request headers to injected HTTP
   * execution.
   *
   * Inputs
   * ------
   * path: string
   *     Notion v1 API path with its leading slash.
   * body: object or undefined
   *     JSON request body; undefined selects GET and a supplied body selects POST.
   *
   * Outputs
   * -------
   * response: Promise<unknown>
   *     Parsed authenticated Notion JSON response; bounded request errors reject.
   */
  const notion = async (path, body) => requestJson(
    `https://api.notion.com/v1${path}`,
    {
      method: body === undefined ? "GET" : "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    },
    http,
  );
  // Require the diary title, canonical URL, project relation, and native people schema
  const schema = await notion(`/data_sources/${encodeURIComponent(dataSourceId)}`);
  const title = titleProperty(schema, "Research Diary");
  if (schema.properties[COMMIT_LINK]?.type !== "url") {
    throw new Error('Research Diary must contain a URL property named exactly "Commit Link".');
  }
  const project = schema.properties.Project;
  if (project?.type !== "relation" || !project.relation?.data_source_id) {
    throw new Error('Research Diary needs a "Project" relation to an accessible Project data source. Share that data source with the integration.');
  }
  const ownerProperty = schema.properties.Owner ? "Owner" : "Person";
  if (schema.properties[ownerProperty]?.type !== "people") {
    throw new Error('Research Diary needs a native people property named "Owner" or "Person".');
  }
  let pageProperties;
  /**
   * Purpose
   * -------
   * Lazily resolve and memoize native project-relation and people-property values.
   *
   * Inputs
   * ------
   * None
   *
   * Outputs
   * -------
   * properties: Promise<object>
   *     Shared project and owner property payload. The promise is initialized only for
   *     a new diary page and reused across commits.
   */
  const getPageProperties = () => pageProperties ??= (async () => {
    const projectId = await resolveProject(notion, project.relation.data_source_id, repository.split("/")[1], log);
    const ownerId = await resolveOwner(notion, env, log);
    return {
      Project: { relation: [{ id: projectId }] },
      [ownerProperty]: { people: [{ object: "user", id: ownerId }] },
    };
  })();
  const context = { notion, dataSourceId, titleProperty: title, getPageProperties, log, seen: new Set() };
  const counts = { created: 0, skipped: 0 };
  // Process commits in order and retain completed work when a later commit fails
  for (const commit of commits) {
    try {
      const result = await processCommit(commit, context);
      counts[result] += 1;
    } catch (error) {
      throw new Error(`Commit ${commit.sha} failed: ${error.message}`);
    }
  }
  log(`Finished: ${counts.created} created, ${counts.skipped} skipped.`);
  return counts;
}

// Execute only when invoked as the script; imports expose testable helpers without publication
if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  /**
   * Purpose
   * -------
   * Report a direct-entrypoint failure through redacted stderr and set a nonzero exit
   * status.
   *
   * Inputs
   * ------
   * error: Error
   *     Rejected run/configuration/request failure.
   *
   * Outputs
   * -------
   * undefined
   *     Emits a sanitized error and sets process.exitCode to one.
   */
  run().catch((error) => {
    safeLog(`ERROR: ${error.message}`, process.env, console.error);
    process.exitCode = 1;
  });
}
