import React, { Fragment, useState } from "react";
import { Button, Modal, Switch, Typography } from "antd";
import { SiteTravisLink } from "../interface";
import "./segment.css";
import { Link } from "gatsby";

interface Prop {
  testName: string;
  owner: string;
  links: Array<SiteTravisLink>;
  visible: boolean;
  onClose: () => void;
  githubState: Map<string, any>;
}

const daysAgo = (t) => (
  (Date.now().valueOf() / 1000 - t) /
  (60 * 60 * 24)
).toFixed(0)

const DetailModal: React.FC<Prop> = ({ testName, owner, links, visible, onClose, githubState }) => {

  const [showFlaky, setShowFlaky] = useState<boolean>(false);
  if (!showFlaky) {
    links = links.filter(l => l.status == "FAILED");
  }

  let markdownBody = links.map(link => `- ${link.sha} ${link.status} [${link.build_env || "link"}](${link.job_url})`).join("\n");
  markdownBody += "\n\n....\nGenerated from flaky test tracker. Please do not edit the signature in this section.\nDataCaseName-" + testName + "-END\n...."
  let githubNewIssueUrl = "https://github.com/ray-project/ray/issues/new?labels=flaky-tracker&title=";
  githubNewIssueUrl += encodeURIComponent("[CI] `" + testName + "` is failing/flaky on master.");
  githubNewIssueUrl += "&body=" + encodeURIComponent(markdownBody);

  const githubExistingUrl = githubState.get(testName)?.url

  return (

    <Modal
      visible={visible}
      onCancel={onClose}
      footer={null}
      width="80%"
      title={
        <React.Fragment>
          <div>Buildkite Links (Newest to Oldest)</div>
          <Typography.Paragraph copyable style={{ marginBottom: "0em" }}>
            {testName}
          </Typography.Paragraph>
          <Typography.Paragraph>
            owner: {owner}
          </Typography.Paragraph>
        </React.Fragment>
      }
    >

      <p></p>
      <p></p>
      <Switch defaultChecked={false} onChange={setShowFlaky}></Switch> Show Flaky Tests
      {githubExistingUrl ?
        <Link to={githubExistingUrl}><Button type="link">Go to GitHub Issue</Button></Link>
        :
        <Link to={githubNewIssueUrl}><Button type="link">Create GitHub Issue</Button></Link>
      }
      <p></p>
      <p></p>

      {
        links.map((link) => (
          <Fragment key={link.job_url}>
            {link.status == "FLAKY" ? <div className="item flaky" ></div> : <div className="item failed"></div>}
            <p>
              {link.sha_short} {link.commit_message} [
              {daysAgo(link.commit_time)}{" "}
              days ago]
            </p>
            <a href={link.job_url}>
              <p
                style={{
                  fontFamily: "monospace",
                  marginLeft: "5%",
                }}
              >
                {link.os} {link.build_env}
              </p>
            </a>
          </Fragment>
        ))
      }
    </Modal >
  );
};

export default DetailModal;
