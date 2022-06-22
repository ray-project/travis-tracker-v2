import React, { useState } from "react";
import { Modal, Switch, Typography } from "antd";
import { SiteTravisLink } from "../interface";
import "./segment.css";

interface Prop {
  testName: string;
  links: Array<SiteTravisLink>;
  visible: boolean;
  onClose: () => void;
}

const DetailModal: React.FC<Prop> = ({ testName, links, visible, onClose }) => {

  const [showFlaky, setShowFlaky] = useState<boolean>(false);
  if (!showFlaky) {
    links = links.filter(l=>l.status == "FAILED");
  }

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
        </React.Fragment>
      }
    >

    <Switch defaultChecked={false} onChange={setShowFlaky}></Switch> Show Flaky Tests
    <p></p>

      {links.map((link) => (
        <>
          {link.status == "FLAKY" ? <div className="item flaky" ></div> : <div className="item failed"></div>}
          <p>
            {link.sha_short} {link.commit_message} [
            {(
              (Date.now().valueOf() / 1000 - link.commit_time) /
              (60 * 60 * 24)
            ).toFixed(0)}{" "}
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
        </>
      ))}
    </Modal>
  );
};

export default DetailModal;
