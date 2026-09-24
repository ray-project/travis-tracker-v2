import { PageProps } from "gatsby";
import React from "react";
import { Alert, Table, Tag, Typography } from "antd";

import LayoutWrapper from "../components/layout";
import Title from "../components/title";
import { SiteNightlyRoot, SiteNightlyRun } from "../interface";
import rawData from "../nightly.json";

const nightlyData = rawData as SiteNightlyRoot;

const GITHUB_COMMIT = "https://github.com/ray-project/ray/commit";

// A run that never produced test jobs (aborted at init, cancelled) must not be
// rendered as a pass — it carries no signal about the wheel either way.
// The verdict comes from Buildkite's own build state, not from a per-job
// tally. Buildkite already aggregates every job in the build into one result,
// and it is the only signal that stays correct when the test jobs never ran at
// all: a job whose dependency failed is neither passed nor failed, so a tally
// that enumerates failure states scores it as a pass.
//
// Build states that mean the run is over. Anything else -- running, scheduled,
// canceling -- is still moving and gets no verdict.
const TERMINAL_STATES = new Set([
  "passed",
  "failed",
  "canceled",
  "blocked",
  "skipped",
  "not_run",
  "finished",
]);

// Age of the feed, rendered as one always-present line rather than a banner
// that appears only when stale. Gatsby evaluates this during `gatsby build`,
// minutes after the feed was written, so a conditional element would be absent
// from the published HTML and inserted only when React hydrates -- a structural
// mismatch, and invisible to anything reading the static page. Keeping the
// element constant and varying only its text avoids that.
const STALE_AFTER_HOURS = 12;

const DataAge: React.FC<{ generatedAt: string }> = ({ generatedAt }) => {
  const parsed = Date.parse(generatedAt);
  // An unparseable timestamp counts as stale. This is the only control telling
  // a reader the feed stopped updating, and `NaN > 12` is false, so comparing
  // without this check would silently switch the warning off in exactly the
  // case where something has gone wrong with the data.
  const unknown = Number.isNaN(parsed);
  const hoursOld = unknown ? Infinity : (Date.now() - parsed) / 36e5;
  const stale = hoursOld > STALE_AFTER_HOURS;

  if (unknown) {
    return (
      <Typography.Paragraph type="warning">
        This page could not read when its data was last refreshed, so it may be
        out of date.
      </Typography.Paragraph>
    );
  }
  return (
    <Typography.Paragraph type={stale ? "warning" : "secondary"}>
      Data refreshed {new Date(parsed).toUTCString()}
      {stale
        ? ` — over ${STALE_AFTER_HOURS} hours ago, so the refresh job may be failing.`
        : "."}
    </Typography.Paragraph>
  );
};

const ResultTag: React.FC<{ run: SiteNightlyRun }> = ({ run }) => {
  if (!TERMINAL_STATES.has(run.state)) {
    return <Tag color="blue">IN PROGRESS</Tag>;
  }
  // A run that never produced test jobs, or was cancelled, has no result to
  // report either way; saying PASSED there would be a false assurance.
  if (run.tests_total === 0 || run.state === "canceled") {
    return <Tag color="default">INCOMPLETE</Tag>;
  }
  if (run.state === "passed") {
    return <Tag color="green">PASSED</Tag>;
  }
  return <Tag color="red">FAILED</Tag>;
};

const App: React.FC<PageProps> = () => {
  const runs = nightlyData.runs;

  const columns = [
    {
      title: "Date",
      dataIndex: "created_at",
      render: (value: string) => value.slice(0, 10),
    },
    {
      title: "Commit",
      dataIndex: "commit",
      render: (commit: string, run: SiteNightlyRun) => (
        <a href={`${GITHUB_COMMIT}/${commit}`} target="_blank" rel="noreferrer">
          <code>{run.commit_short}</code>
        </a>
      ),
    },
    {
      title: "Result",
      key: "result",
      render: (_: unknown, run: SiteNightlyRun) => <ResultTag run={run} />,
    },
    {
      title: "Nightly wheel",
      dataIndex: "wheel_base",
      // The bucket serves no HTML index, so this is an S3 ListObjectsV2 query:
      // it renders as an XML listing of every wheel built for the commit. Say
      // so in the tooltip, because the destination is not a normal web page.
      render: (wheelBase: string) =>
        wheelBase ? (
          <a
            href={wheelBase}
            target="_blank"
            rel="noreferrer"
            title="Lists every wheel built for this commit (raw S3 XML listing)"
          >
            wheels
          </a>
        ) : null,
    },
    {
      title: "Docker image",
      dataIndex: "image_tags_url",
      // Blank when DockerHub has aged the nightly tags out (~5 months). Say so
      // rather than leaving the cell empty, which reads as a rendering fault.
      render: (url: string) =>
        url ? (
          <a href={url} target="_blank" rel="noreferrer">
            images
          </a>
        ) : (
          <span
            style={{ color: "rgba(0,0,0,0.35)" }}
            title="Nightly images for this commit are no longer on DockerHub"
          >
            n/a
          </span>
        ),
    },
  ];

  return (
    <LayoutWrapper>
      <Title></Title>

      <Typography.Title level={2}>Nightly release test status</Typography.Title>

      <Alert
        type="info"
        showIcon
        message="How to read this page"
        description={
          <>
            Each row is one scheduled run of Ray's release tests against a
            master commit, and the wheel built from that commit. A run covers
            roughly 265 release tests. Most failing nights are one or two
            flaky or infrastructure-related tests rather than a broken wheel, so
            check the failure count and the test names before drawing a
            conclusion.
          </>
        }
        style={{ marginBottom: "1rem" }}
      />

      <Table
        dataSource={runs}
        columns={columns}
        rowKey={(run) => String(run.build_number)}
        pagination={{ pageSize: 30 }}
      />

      <DataAge generatedAt={nightlyData.generated_at} />
    </LayoutWrapper>
  );
};

export default App;
