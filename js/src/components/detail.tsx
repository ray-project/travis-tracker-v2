import React from "react";
import { Modal, Typography } from "antd";
import { SiteTravisLink } from "../interface";

interface Prop {
  testName: string;
  links: Array<SiteTravisLink>;
  visible: boolean;
  onClose: () => void;
}

const DetailModal: React.FC<Prop> = ({ testName, links, visible, onClose }) => {
  return (
    <Modal
      visible={visible}
      onCancel={onClose}
      footer={null}
      width="80%"
      title={
        <React.Fragment>
          <div>Travis Links (Newest to Oldest)</div>
          <Typography.Paragraph copyable style={{ marginBottom: "0em" }}>
            {testName}
          </Typography.Paragraph>
        </React.Fragment>
      }
    >
      {links.map((link) => (
        <>
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
