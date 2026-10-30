/**
 * Purpose
 * -------
 * Verify the diary publisher with temporary event files and injected in-memory service
 * behavior.
 *
 * Inputs
 * ------
 * None
 *
 * Outputs
 * -------
 * Registered node:test regression cases
 *     The publisher network dependency is mocked. The subprocess entrypoint test omits
 *     NOTION_TOKEN and fails before any request can be made.
 */
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { NOTION_VERSION, run, safeLog } from "./notion-research-diary.mjs";

const SHA_A = "a".repeat(40);
const SHA_B = "b".repeat(40);
const SHA_C = "c".repeat(40);
const REPOSITORY = "example/research";
const DATA_SOURCE_ID = "example-data-source";
const PROJECT_DATA_SOURCE_ID = "example-projects";
const PROJECT_ID = "11111111-1111-4111-8111-111111111111";
const OWNER_ID = "22222222-2222-4222-8222-222222222222";
/**
 * Purpose
 * -------
 * Construct the canonical permanent URL used by the in-memory diary assertions.
 *
 * Inputs
 * ------
 * sha: string
 *     Fixture commit SHA.
 *
 * Outputs
 * -------
 * url: string
 *     Example repository commit URL.
 */
const commitUrl = (sha) => `https://github.com/${REPOSITORY}/commit/${sha}`;
/**
 * Purpose
 * -------
 * Construct one minimal native Notion project-page fixture.
 *
 * Inputs
 * ------
 * name: string
 *     Native project title.
 * id: string, optional
 *     Project page identifier, defaulting to PROJECT_ID.
 *
 * Outputs
 * -------
 * page: object
 *     Fake project page with its native title property.
 */
const project = (name, id = PROJECT_ID) => ({ id, properties: { Project: { title: [{ plain_text: name }] } } });
/**
 * Purpose
 * -------
 * Construct a nondeletion push payload from explicit fixture commits.
 *
 * Inputs
 * ------
 * commits: Array<object>
 *     Commit records supplied as positional arguments.
 *
 * Outputs
 * -------
 * event: object
 *     Push payload containing deleted=false and the complete commit collection.
 */
const push = (...commits) => ({ deleted: false, commits });
/**
 * Purpose
 * -------
 * Construct one commit-event fixture with an explicit subject/body message.
 *
 * Inputs
 * ------
 * id: string
 *     Commit identifier.
 * message: string, optional
 *     Full fixture commit message.
 *
 * Outputs
 * -------
 * commit: object
 *     Event id/message record.
 */
const commit = (id, message = "Commit subject\n\nCommit body") => ({ id, message });
/**
 * Purpose
 * -------
 * Construct a local JSON Response for injected HTTP behavior.
 *
 * Inputs
 * ------
 * body: unknown
 *     JSON-serializable mock API body.
 * status: number, optional
 *     HTTP response status.
 * headers: object, optional
 *     Mock response headers, including Retry-After when needed.
 *
 * Outputs
 * -------
 * response: Response
 *     In-memory response; no network operation occurs.
 */
const response = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), { status, headers });

/**
 * Purpose
 * -------
 * Create an isolated temporary Actions event and entirely injected in-memory
 * GitHub/Notion service.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Registers removal of the temporary directory after the test.
 * event: object
 *     Initial JSON event payload.
 * eventName: string, optional
 *     Actions source, normally push or workflow_dispatch.
 *
 * Outputs
 * -------
 * fixture: Promise<object>
 *     Fake environment, request/log/delay inventories, in-memory pages, mutable mock
 *     behavior, event writer, and injected execute callback.
 */
async function fixture(t, event, eventName = "push") {
  const directory = await mkdtemp(join(tmpdir(), "notion-research-diary-"));
  // Remove only this test-owned temporary event directory after the case finishes
  t.after(() => rm(directory, { recursive: true, force: true }));
  const eventPath = join(directory, "event.json");
  const env = {
    GITHUB_EVENT_NAME: eventName,
    GITHUB_EVENT_PATH: eventPath,
    GITHUB_REPOSITORY: REPOSITORY,
    GITHUB_SHA: SHA_B,
    GITHUB_REF: "refs/heads/feature/foo",
    GITHUB_TOKEN: "test-github-token",
    NOTION_TOKEN: "test-notion-token",
    NOTION_DATA_SOURCE_ID: DATA_SOURCE_ID,
  };
  const logs = [];
  const waits = [];
  const requests = [];
  const pages = new Map();
  // Keep schemas, source metadata, failure modes, and pagination under explicit test control
  const state = {
    schema: { properties: {
      "Entry name": { type: "title" }, "Commit Link": { type: "url" },
      Project: { type: "relation", relation: { data_source_id: PROJECT_DATA_SOURCE_ID } },
      Person: { type: "people" }, Date: { type: "created_time" },
    } },
    projectSchema: { properties: { Project: { type: "title" } } },
    projects: [project("research")],
    projectQueryOverride: null,
    users: [{ object: "user", type: "person", id: OWNER_ID, name: "Julio Morales" }],
    userStatus: 200,
    userPages: null,
    githubCommit: { sha: SHA_A, commit: { message: "Manual subject\n\nActual body from GitHub" } },
    githubStatus: 200,
    failCreateUrl: null,
    ambiguousCreate: false,
    rateLimit: false,
    queryOverride: null,
  };
  /**
   * Purpose
   * -------
   * Route every injected request to local mock state while checking request contracts.
   *
   * Inputs
   * ------
   * url: string
   *     Expected GitHub or Notion endpoint generated by the tested module.
   * options: object
   *     Method, headers, optional JSON body, redirect policy, and AbortSignal.
   *
   * Outputs
   * -------
   * response: Promise<Response>
   *     Local fixture response or simulated transport error. All requests are recorded
   *     in memory; this adapter makes no network calls.
   */
  const fetchImpl = async (url, options) => {
    const body = options.body ? JSON.parse(options.body) : undefined;
    requests.push({ url, ...options, body });
    assert.equal(options.redirect, "error");
    assert.ok(options.signal instanceof AbortSignal);
    // Simulate repository commit resolution and verify its pinned request headers
    if (url.startsWith("https://api.github.com/")) {
      assert.equal(options.method, "GET");
      assert.equal(options.headers.Authorization, `Bearer ${env.GITHUB_TOKEN}`);
      assert.equal(options.headers["X-GitHub-Api-Version"], "2026-03-10");
      assert.ok(url.includes("/commits/"));
      return response(state.githubStatus === 200 ? state.githubCommit : { message: "No commit found for SHA" }, state.githubStatus);
    }
    assert.ok(url.startsWith("https://api.notion.com/v1/"), `Unexpected request: ${url}`);
    assert.equal(options.headers.Authorization, `Bearer ${env.NOTION_TOKEN}`);
    assert.equal(options.headers["Notion-Version"], NOTION_VERSION);
    const path = new URL(url).pathname;
    // Simulate native user lookup and optional paginated results without external I/O
    if (path === "/v1/users" || path.startsWith("/v1/users/")) {
      assert.equal(options.method, "GET");
      if (state.userStatus !== 200) return response({ code: "restricted_resource", message: "Enable user information capabilities" }, state.userStatus);
      if (path.startsWith("/v1/users/")) return response(state.users.find((user) => user.id === path.split("/").at(-1)) ?? {});
      if (state.userPages) return response(state.userPages(new URL(url).searchParams.get("start_cursor")));
      return response({ results: state.users, has_more: false });
    }
    // Resolve the fake project schema and exact-title query behavior
    if (path === `/v1/data_sources/${PROJECT_DATA_SOURCE_ID}`) return response(state.projectSchema);
    if (path === `/v1/data_sources/${PROJECT_DATA_SOURCE_ID}/query`) {
      assert.equal(options.method, "POST");
      assert.equal(body.filter.property, "Project");
      assert.equal(body.page_size, 2);
      if (state.projectQueryOverride) return state.projectQueryOverride(body);
      return response({ results: state.projects.filter((page) => page.properties.Project.title[0].plain_text.toLowerCase() === body.filter.title.equals.toLowerCase()), has_more: false });
    }
    if (path === `/v1/data_sources/${DATA_SOURCE_ID}`) {
      assert.equal(options.method, "GET");
      return response(state.schema);
    }
    // Simulate canonical-link duplicate queries, explicit rate limits, and failures
    if (path === `/v1/data_sources/${DATA_SOURCE_ID}/query`) {
      assert.equal(options.method, "POST");
      assert.equal(body.filter.property, "Commit Link");
      assert.equal(body.page_size, 1);
      if (state.rateLimit) {
        state.rateLimit = false;
        return response({ code: "rate_limited", message: "Slow down" }, 429, { "Retry-After": "2" });
      }
      if (state.queryOverride) return state.queryOverride();
      const page = pages.get(body.filter.url.equals);
      return response({ results: page ? [page] : [] });
    }
    // Create pages only in the fixture map and optionally simulate an ambiguous accepted write
    assert.equal(path, "/v1/pages");
    assert.equal(options.method, "POST");
    const urlKey = body.properties["Commit Link"].url;
    if (state.failCreateUrl === urlKey) {
      return response({ code: "service_unavailable", message: "Try again later", request_id: "example-request" }, 503);
    }
    assert.ok(!pages.has(urlKey), `Attempted duplicate creation: ${urlKey}`);
    const page = { object: "page", id: `page-${pages.size + 1}`, ...body };
    pages.set(urlKey, page);
    if (state.ambiguousCreate) {
      state.ambiguousCreate = false;
      throw new Error("Connection lost after page was accepted");
    }
    return response(page);
  };
  /**
   * Purpose
   * -------
   * Replace the temporary event file and selected mock Actions event name.
   *
   * Inputs
   * ------
   * nextEvent: object
   *     New JSON event payload.
   * nextName: string, optional
   *     New event source, defaulting to the current fixture event name.
   *
   * Outputs
   * -------
   * result: Promise<void>
   *     Resolves after the local event JSON is written and fixture state updated.
   */
  const setEvent = async (nextEvent, nextName = env.GITHUB_EVENT_NAME) => {
    env.GITHUB_EVENT_NAME = nextName;
    await writeFile(eventPath, JSON.stringify(nextEvent));
  };
  await setEvent(event, eventName);
  return {
    env, logs, waits, requests, pages, state, setEvent,
    /**
     * Purpose
     * -------
     * Run the publisher exclusively through captured fixture HTTP, delay, environment,
     * and log dependencies.
     *
     * Inputs
     * ------
     * None
     *
     * Outputs
     * -------
     * counts: Promise<object>
     *     Test run created/skipped counts; mock API interactions and delays are
     *     recorded without external requests or real waiting.
     */
    execute: () => run({ env, fetchImpl, wait: async (ms) => waits.push(ms), output: (line) => logs.push(line) }),
  };
}

/**
 * Purpose
 * -------
 * Verify push processes every commit, using only its subject and canonical permanent
 * URL.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("push processes every commit, using only its subject and canonical permanent URL", async (t) => {
  const f = await fixture(t, {
    ...push(
      { ...commit(SHA_A, "Subject A\n\nBody A"), url: "https://untrusted.example/wrong" },
      commit(SHA_B, "Subject B\r\nBody B"),
      commit(SHA_C, 'Subject C $(echo unsafe) `echo unsafe` "quoted"\rBody C'),
    ),
    head_commit: commit(SHA_C, "Do not use head_commit"),
  });
  assert.deepEqual(await f.execute(), { created: 3, skipped: 0 });
  const titles = [...f.pages.values()].map((page) => page.properties["Entry name"].title.map((text) => text.text.content).join(""));
  assert.deepEqual(titles, ["Subject A", "Subject B", 'Subject C $(echo unsafe) `echo unsafe` "quoted"']);
  for (const sha of [SHA_A, SHA_B, SHA_C]) {
    const page = f.pages.get(commitUrl(sha));
    assert.deepEqual(page.parent, { type: "data_source_id", data_source_id: DATA_SOURCE_ID });
    assert.deepEqual(page.properties["Commit Link"], { url: commitUrl(sha) });
    assert.deepEqual(Object.keys(page.properties), ["Entry name", "Commit Link", "Project", "Person"]);
    assert.deepEqual(page.properties.Project, { relation: [{ id: PROJECT_ID }] });
    assert.deepEqual(page.properties.Person, { people: [{ object: "user", id: OWNER_ID }] });
    assert.equal(page.properties.Date, undefined);
  }
  const queries = f.requests.filter((request) => request.url.endsWith(`/data_sources/${DATA_SOURCE_ID}/query`));
  assert.deepEqual(queries.map((request) => request.body.filter), [SHA_A, SHA_B, SHA_C].map((sha) => ({ property: "Commit Link", url: { equals: commitUrl(sha) } })));
  assert.equal(f.requests.filter((request) => request.url.includes("/commits/")).length, 0);
  assert.equal(f.requests.filter((request) => request.url.startsWith("https://api.github.com")).length, 0);
  assert.ok(f.logs.some((line) => line.includes("Execution source: push")));
  assert.equal(f.logs.filter((line) => line.includes("Created Research Diary")).length, 3);
});

/**
 * Purpose
 * -------
 * Verify the same commit on main, develop, feature, experiment, or a new branch is
 * skipped.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("the same commit on main, develop, feature, experiment, or a new branch is skipped", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  assert.deepEqual(await f.execute(), { created: 1, skipped: 0 });
  for (const branch of ["main", "develop", "feature/foo", "experiment/bar", "new-branch"]) {
    f.env.GITHUB_REF = `refs/heads/${branch}`;
    await f.setEvent({ ...push(commit(SHA_A)), created: branch === "new-branch" });
    assert.deepEqual(await f.execute(), { created: 0, skipped: 1 });
  }
  assert.equal(f.pages.size, 1);
  assert.equal(f.logs.filter((line) => line.includes("Skipped existing commit")).length, 5);
});

/**
 * Purpose
 * -------
 * Verify a repeated SHA in one payload is also safe without relying on query
 * visibility.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("a repeated SHA in one payload is also safe without relying on query visibility", async (t) => {
  const f = await fixture(t, push(commit(SHA_A), commit(SHA_A)));
  assert.deepEqual(await f.execute(), { created: 1, skipped: 1 });
  assert.equal(f.requests.filter((request) => request.url.endsWith(`/data_sources/${DATA_SOURCE_ID}/query`)).length, 1);
});

/**
 * Purpose
 * -------
 * Verify manual commit_sha resolves an abbreviation to one full SHA and uses GitHub's
 * message.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("manual commit_sha resolves an abbreviation to one full SHA and uses GitHub's message", async (t) => {
  const f = await fixture(t, { inputs: { commit_sha: SHA_A.slice(0, 10).toUpperCase() }, commits: [commit(SHA_C)] }, "workflow_dispatch");
  assert.deepEqual(await f.execute(), { created: 1, skipped: 0 });
  assert.ok(f.requests[0].url.endsWith(`/commits/${SHA_A.slice(0, 10).toUpperCase()}`));
  assert.equal(f.pages.get(commitUrl(SHA_A)).properties["Entry name"].title[0].text.content, "Manual subject");
  assert.ok(f.logs.some((line) => line.includes("manual-test mode")));
  assert.ok(f.logs.some((line) => line.includes("commit_sha input")));
  assert.deepEqual(await f.execute(), { created: 0, skipped: 1 });
  assert.equal(f.pages.size, 1);
});

/**
 * Purpose
 * -------
 * Verify empty manual input resolves the dispatched HEAD snapshot and repeated runs
 * skip it.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("empty manual input resolves the dispatched HEAD snapshot and repeated runs skip it", async (t) => {
  const f = await fixture(t, { inputs: { commit_sha: "" } }, "workflow_dispatch");
  f.state.githubCommit = { sha: SHA_B, commit: { message: "Selected branch HEAD\nBody" } };
  assert.deepEqual(await f.execute(), { created: 1, skipped: 0 });
  assert.ok(f.requests[0].url.endsWith(`/commits/${SHA_B}`));
  assert.ok(f.logs.some((line) => line.includes("HEAD selected for refs/heads/feature/foo")));
  assert.deepEqual(await f.execute(), { created: 0, skipped: 1 });
  assert.equal(f.pages.size, 1);
});

/**
 * Purpose
 * -------
 * Verify manual execution skips an entry previously created by a push.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("manual execution skips an entry previously created by a push", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  await f.execute();
  await f.setEvent({ inputs: { commit_sha: SHA_A } }, "workflow_dispatch");
  assert.deepEqual(await f.execute(), { created: 0, skipped: 1 });
  assert.equal(f.pages.size, 1);
});

/**
 * Purpose
 * -------
 * Verify a nonexistent manual SHA fails clearly before any Notion call.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("a nonexistent manual SHA fails clearly before any Notion call", async (t) => {
  const f = await fixture(t, { inputs: { commit_sha: SHA_A } }, "workflow_dispatch");
  f.state.githubStatus = 404;
  await assert.rejects(f.execute(), /Cannot resolve manual commit.*HTTP 404.*No commit found/);
  assert.equal(f.requests.length, 1);
  assert.equal(f.pages.size, 0);
});

/**
 * Purpose
 * -------
 * Verify malformed manual SHA is rejected without executing input or calling APIs.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("malformed manual SHA is rejected without executing input or calling APIs", async (t) => {
  const f = await fixture(t, { inputs: { commit_sha: "$(echo unsafe)" } }, "workflow_dispatch");
  await assert.rejects(f.execute(), /Cannot resolve manual commit_sha.*hexadecimal abbreviation/);
  assert.equal(f.requests.length, 0);
});

/**
 * Purpose
 * -------
 * Verify gitHub must return the requested manual commit.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("GitHub must return the requested manual commit", async (t) => {
  const f = await fixture(t, { inputs: { commit_sha: SHA_B } }, "workflow_dispatch");
  await assert.rejects(f.execute(), /GitHub returned a different SHA/);
  assert.equal(f.requests.length, 1);
});

/**
 * Purpose
 * -------
 * Verify deletion pushes ignore even attached commits and need no credentials.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("deletion pushes ignore even attached commits and need no credentials", async (t) => {
  const f = await fixture(t, { ...push(commit(SHA_A)), deleted: true });
  delete f.env.NOTION_TOKEN;
  delete f.env.NOTION_DATA_SOURCE_ID;
  delete f.env.GITHUB_REPOSITORY;
  assert.deepEqual(await f.execute(), { created: 0, skipped: 0 });
  assert.equal(f.requests.length, 0);
  assert.ok(f.logs.some((line) => line.includes("Ignored deletion push")));
});

/**
 * Purpose
 * -------
 * Verify empty or missing commit collections are graceful no-ops without credentials.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("empty or missing commit collections are graceful no-ops without credentials", async (t) => {
  const f = await fixture(t, push());
  delete f.env.NOTION_TOKEN;
  delete f.env.NOTION_DATA_SOURCE_ID;
  for (const event of [push(), {}]) {
    await f.setEvent(event);
    assert.deepEqual(await f.execute(), { created: 0, skipped: 0 });
  }
  assert.equal(f.requests.length, 0);
  assert.ok(f.logs.some((line) => line.includes("zero commits")));
});

/**
 * Purpose
 * -------
 * Verify partial failure exposes HTTP details and reruns recover without duplicating
 * prior pages.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("partial failure exposes HTTP details and reruns recover without duplicating prior pages", async (t) => {
  const f = await fixture(t, push(commit(SHA_A), commit(SHA_B), commit(SHA_C)));
  f.state.failCreateUrl = commitUrl(SHA_B);
  await assert.rejects(f.execute(), /Commit b{40} failed:.*HTTP 503.*service_unavailable.*example-request/);
  assert.deepEqual([...f.pages.keys()], [commitUrl(SHA_A)]);
  f.state.failCreateUrl = null;
  assert.deepEqual(await f.execute(), { created: 2, skipped: 1 });
  assert.equal(f.pages.size, 3);
});

/**
 * Purpose
 * -------
 * Verify an ambiguous create failure is not retried and a later rerun finds the
 * accepted page.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("an ambiguous create failure is not retried and a later rerun finds the accepted page", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  f.state.ambiguousCreate = true;
  await assert.rejects(f.execute(), /Connection lost after page was accepted/);
  assert.equal(f.requests.filter((request) => request.url.endsWith("/pages")).length, 1);
  assert.deepEqual(await f.execute(), { created: 0, skipped: 1 });
  assert.equal(f.pages.size, 1);
});

/**
 * Purpose
 * -------
 * Verify duplicate lookup failure must fail instead of creating a page.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("duplicate lookup failure must fail instead of creating a page", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  /**
   * Purpose
   * -------
   * Simulate an explicit duplicate-lookup permission failure before page creation.
   *
   * Inputs
   * ------
   * None
   *
   * Outputs
   * -------
   * response: Response
   *     Local HTTP 403 permission-error fixture.
   */
  f.state.queryOverride = () => response({ code: "restricted_resource", message: "Grant integration access" }, 403);
  await assert.rejects(f.execute(), /HTTP 403.*Grant integration access/);
  assert.equal(f.pages.size, 0);
});

/**
 * Purpose
 * -------
 * Verify rate limiting honors Retry-After and resumes the same duplicate check.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("rate limiting honors Retry-After and resumes the same duplicate check", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  f.state.rateLimit = true;
  assert.deepEqual(await f.execute(), { created: 1, skipped: 0 });
  assert.deepEqual(f.waits, [2000]);
  assert.ok(f.logs.some((line) => line.includes("HTTP 429")));
});

/**
 * Purpose
 * -------
 * Verify persistent rate limiting fails after bounded retries.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("persistent rate limiting fails after bounded retries", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  /**
   * Purpose
   * -------
   * Simulate persistent explicit rate limiting to exercise the bounded retry path.
   *
   * Inputs
   * ------
   * None
   *
   * Outputs
   * -------
   * response: Response
   *     Local HTTP 429 fixture with a one-second Retry-After header.
   */
  f.state.queryOverride = () => response({ code: "rate_limited" }, 429, { "Retry-After": "1" });
  await assert.rejects(f.execute(), /HTTP 429.*rate_limited/);
  assert.deepEqual(f.waits, [1000, 1000, 1000]);
  assert.equal(f.pages.size, 0);
});

/**
 * Purpose
 * -------
 * Verify wrong Notion property types fail before any page writes.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("wrong Notion property types fail before any page writes", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  f.state.schema.properties["Commit Link"].type = "rich_text";
  await assert.rejects(f.execute(), /URL property named exactly "Commit Link"/);
  delete f.state.schema.properties["Commit Link"];
  await assert.rejects(f.execute(), /URL property named exactly "Commit Link"/);
  f.state.schema.properties = { "Commit Link": { type: "url" } };
  await assert.rejects(f.execute(), /exactly one title property/);
  assert.equal(f.pages.size, 0);
});

/**
 * Purpose
 * -------
 * Verify malformed Notion JSON and duplicate-query results fail safely.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("malformed Notion JSON and duplicate-query results fail safely", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  /**
   * Purpose
   * -------
   * Simulate successful HTTP transport with a malformed non-JSON duplicate-query body.
   *
   * Inputs
   * ------
   * None
   *
   * Outputs
   * -------
   * response: Response
   *     Local response that must be rejected by JSON parsing.
   */
  f.state.queryOverride = () => new Response("not-json");
  await assert.rejects(f.execute(), /HTTP 200; invalid JSON/);
  /**
   * Purpose
   * -------
   * Simulate a decoded duplicate-query response with an invalid results shape.
   *
   * Inputs
   * ------
   * None
   *
   * Outputs
   * -------
   * response: Response
   *     Local JSON body whose null results must prevent page creation.
   */
  f.state.queryOverride = () => response({ results: null });
  await assert.rejects(f.execute(), /Invalid Notion duplicate-query response/);
  assert.equal(f.pages.size, 0);
});

/**
 * Purpose
 * -------
 * Verify long Unicode subjects are preserved in valid-size rich-text chunks.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("long Unicode subjects are preserved in valid-size rich-text chunks", async (t) => {
  const subject = "🌞".repeat(2001);
  const f = await fixture(t, push(commit(SHA_A, `${subject}\nBody must not become title`)));
  await f.execute();
  const chunks = f.pages.get(commitUrl(SHA_A)).properties["Entry name"].title;
  assert.equal(chunks.map((part) => part.text.content).join(""), subject);
  assert.ok(chunks.every((part) => part.text.content.length <= 2000));
});

/**
 * Purpose
 * -------
 * Verify missing credentials, malformed push metadata, and unsupported events fail
 * clearly.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("missing credentials, malformed push metadata, and unsupported events fail clearly", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  delete f.env.NOTION_TOKEN;
  await assert.rejects(f.execute(), /Missing NOTION_TOKEN/);
  await f.setEvent(push(commit("short-sha")));
  await assert.rejects(f.execute(), /full 40-character commit SHA/);
  await f.setEvent({ commits: "not-an-array" });
  await assert.rejects(f.execute(), /push.commits must be an array/);
  await f.setEvent({}, "pull_request");
  await assert.rejects(f.execute(), /Unsupported event: pull_request/);
  assert.equal(f.requests.length, 0);
});

/**
 * Purpose
 * -------
 * Verify log output redacts secrets and cannot introduce Actions command lines.
 *
 * Inputs
 * ------
 * None
 *
 * Outputs
 * -------
 * undefined
 *     Completes after all local assertions; failed expectations throw an assertion
 *     error.
 */
test("log output redacts secrets and cannot introduce Actions command lines", () => {
  const output = [];
  const env = { NOTION_TOKEN: "token-value", GITHUB_TOKEN: "github-value", NOTION_DATA_SOURCE_ID: "source-value", NOTION_OWNER_USER_ID: "owner-value" };
  safeLog("HTTP 401 token-value github-value source-value owner-value\n::error::forged\rmessage", env, (line) => output.push(line));
  assert.equal(output[0], "[research-diary] HTTP 401 [REDACTED] [REDACTED] [REDACTED] [REDACTED]\\n::error::forged\\rmessage");
});

/**
 * Purpose
 * -------
 * Verify project lookup prefers the literal repository name and accepts its readable
 * spelling.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("project lookup prefers the literal repository name and accepts its readable spelling", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  f.env.GITHUB_REPOSITORY = "example/Morales_2025a";
  f.state.projects = [project("Morales_2025a"), project("Morales 2025a", "another-project")];
  await f.execute();
  assert.equal([...f.pages.values()][0].properties.Project.relation[0].id, PROJECT_ID);
  assert.equal(f.requests.filter((request) => request.url.endsWith(`/data_sources/${PROJECT_DATA_SOURCE_ID}/query`)).length, 1);
  f.pages.clear();
  f.state.projects = [project("Morales 2025a")];
  await f.execute();
  assert.equal([...f.pages.values()][0].properties.Project.relation[0].id, PROJECT_ID);
  assert.ok(f.logs.some((line) => line.includes('Resolved project: "Morales 2025a"')));
});

/**
 * Purpose
 * -------
 * Verify missing or ambiguous project matches fail before creating pages.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("missing or ambiguous project matches fail before creating pages", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  f.state.projects = [project("different project")];
  await assert.rejects(f.execute(), /No Notion project matches repository/);
  f.state.projects = [project("research"), project("research", "duplicate-project")];
  await assert.rejects(f.execute(), /Multiple Notion projects match/);
  assert.equal(f.pages.size, 0);
});

/**
 * Purpose
 * -------
 * Verify matching repositories use their own projects and commit URLs in the shared
 * diary.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("matching repositories use their own projects and commit URLs in the shared diary", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  const repositories = [
    ["Morales_2023", "Morales 2023"],
    ["Morales_2025a", "Morales 2025a"],
    ["Morales_202xa", "Morales 202xa"],
    ["Vesa_2026", "Vesa 2026"],
    ["another-repository", "another repository"],
  ];
  f.state.projects = repositories.map(([, name], index) => project(name, `project-${index}`));
  for (const [index, [repository]] of repositories.entries()) {
    f.env.GITHUB_REPOSITORY = `example/${repository}`;
    assert.deepEqual(await f.execute(), { created: 1, skipped: 0 });
    const url = `https://github.com/example/${repository}/commit/${SHA_A}`;
    assert.deepEqual(f.pages.get(url).properties.Project, { relation: [{ id: `project-${index}` }] });
    assert.equal(f.pages.get(url).properties["Commit Link"].url, url);
    assert.deepEqual(await f.execute(), { created: 0, skipped: 1 });
  }
  assert.equal(f.pages.size, repositories.length);
});

/**
 * Purpose
 * -------
 * Verify owner resolution uses native people and supports the full name or verified
 * display name.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("owner resolution uses native people and supports the full name or verified display name", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  f.state.users = [
    { type: "bot", id: "bot-id", name: "Julio M. Morales" },
    { type: "person", id: OWNER_ID, name: "Julio M. Morales" },
  ];
  await f.execute();
  assert.deepEqual(f.pages.get(commitUrl(SHA_A)).properties.Person, { people: [{ object: "user", id: OWNER_ID }] });
});

/**
 * Purpose
 * -------
 * Verify user lookup follows pagination and rejects missing or ambiguous people.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("user lookup follows pagination and rejects missing or ambiguous people", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  /**
   * Purpose
   * -------
   * Provide a deterministic two-page native-user response to the injected mock adapter.
   *
   * Inputs
   * ------
   * cursor: string or null
   *     Requested fixture pagination cursor.
   *
   * Outputs
   * -------
   * page: object
   *     Next mocked user page or the initial continuation page.
   */
  f.state.userPages = (cursor) => cursor
    ? { results: f.state.users, has_more: false }
    : { results: [{ type: "person", name: "Someone else", id: "someone-else" }], has_more: true, next_cursor: "next-users" };
  await f.execute();
  assert.ok(f.requests.some((request) => request.url.includes("start_cursor=next-users")));
  f.pages.clear();
  f.state.userPages = null;
  f.state.users = [];
  await assert.rejects(f.execute(), /Expected one Notion person/);
  f.state.users = [
    { type: "person", id: OWNER_ID, name: "Julio Morales" },
    { type: "person", id: "another-user", name: "Julio M. Morales" },
  ];
  await assert.rejects(f.execute(), /Configure NOTION_OWNER_USER_ID/);
  assert.equal(f.pages.size, 0);
});

/**
 * Purpose
 * -------
 * Verify configured native user ID disambiguates accounts and rejects bot owners.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("configured native user ID disambiguates accounts and rejects bot owners", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  f.env.NOTION_OWNER_USER_ID = OWNER_ID;
  f.state.users.push({ type: "person", id: "another-user", name: "Julio Morales" });
  await f.execute();
  assert.ok(f.requests.some((request) => request.url.endsWith(`/users/${OWNER_ID}`)));
  assert.equal(f.requests.filter((request) => request.url.includes("/users?")).length, 0);
  f.pages.clear();
  f.state.users[0].type = "bot";
  await assert.rejects(f.execute(), /person, not an integration bot/);
  f.env.NOTION_OWNER_USER_ID = "not-a-user-uuid";
  await assert.rejects(f.execute(), /native Notion user UUID/);
});

/**
 * Purpose
 * -------
 * Verify missing user information capability fails visibly without a page write.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("missing user information capability fails visibly without a page write", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  f.state.userStatus = 403;
  await assert.rejects(f.execute(), /HTTP 403.*Enable user information capabilities/);
  assert.equal(f.pages.size, 0);
});

/**
 * Purpose
 * -------
 * Verify automatic Date is left to Notion and a native Owner field is used when
 * present.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("automatic Date is left to Notion and a native Owner field is used when present", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  f.state.schema.properties.Owner = { type: "people" };
  await f.execute();
  const properties = f.pages.get(commitUrl(SHA_A)).properties;
  assert.equal(properties.Date, undefined);
  assert.deepEqual(properties.Owner, { people: [{ object: "user", id: OWNER_ID }] });
  assert.equal(properties.Person, undefined);
});

/**
 * Purpose
 * -------
 * Verify repeated manual execution skips existing pages without repeating enrichment
 * lookups.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("repeated manual execution skips existing pages without repeating enrichment lookups", async (t) => {
  const f = await fixture(t, { inputs: { commit_sha: SHA_A } }, "workflow_dispatch");
  await f.execute();
  f.state.users = [];
  f.state.projects = [];
  assert.deepEqual(await f.execute(), { created: 0, skipped: 1 });
  assert.equal(f.pages.size, 1);
  assert.equal(f.pages.get(commitUrl(SHA_A)).properties.Date, undefined);
});

/**
 * Purpose
 * -------
 * Verify project and people schemas are required before creating pages.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("project and people schemas are required before creating pages", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  f.state.schema.properties.Project.relation = {};
  await assert.rejects(f.execute(), /Project.*accessible Project data source/);
  f.state.schema.properties.Project.relation = { data_source_id: PROJECT_DATA_SOURCE_ID };
  f.state.schema.properties.Person.type = "rich_text";
  await assert.rejects(f.execute(), /native people property/);
  assert.equal(f.pages.size, 0);
});

/**
 * Purpose
 * -------
 * Verify the script entrypoint reports configuration failure and exits nonzero.
 *
 * Inputs
 * ------
 * t: node:test TestContext
 *     Test lifecycle used by the isolated fixture.
 *
 * Outputs
 * -------
 * result: Promise<void>
 *     Resolves after all local regression assertions; failed expectations reject the
 *     test.
 */
test("the script entrypoint reports configuration failure and exits nonzero", async (t) => {
  const f = await fixture(t, push(commit(SHA_A)));
  const script = fileURLToPath(new URL("./notion-research-diary.mjs", import.meta.url));
  // Omit the required Notion token so the real entrypoint exits before any network request
  const result = spawnSync(process.execPath, [script], {
    env: { ...f.env, NOTION_TOKEN: "" },
    encoding: "utf8",
    timeout: 10_000,
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /ERROR: Missing NOTION_TOKEN/);
  assert.doesNotMatch(result.stdout + result.stderr, /test-github-token|test-notion-token/);
});
