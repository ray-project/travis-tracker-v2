import { PageProps } from "gatsby";
import React from "react";
import { Alert, Col, Row, Table, Tag, Typography } from "antd";

import LayoutWrapper from "../components/layout";
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

  const generated = new Date(nightlyData.generated_at);
  const hoursOld = (Date.now() - generated.getTime()) / 36e5;

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
      <Row justify="space-around" align="middle">
        <Col flex="auto">
          <Typography.Title level={1}>
            Ray Nightly Release Test Status
          </Typography.Title>
        </Col>
      </Row>

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

      {hoursOld > 12 && (
        <Alert
          type="warning"
          showIcon
          message={`This data is ${Math.floor(
            hoursOld
          )} hours old — the refresh job may be failing.`}
          style={{ marginBottom: "1rem" }}
        />
      )}

      <Table
        dataSource={runs}
        columns={columns}
        rowKey={(run) => String(run.build_number)}
        pagination={{ pageSize: 30 }}
      />

      <Typography.Paragraph type="secondary">
        Last updated {nightlyData.generated_at}.
      </Typography.Paragraph>
    </LayoutWrapper>
  );
};

export default App;
