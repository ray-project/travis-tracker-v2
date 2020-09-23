import React from "react";
import { Modal } from "antd";
import { SiteTravisLink } from "../interface";

interface Prop {
  links: Array<SiteTravisLink>;
  visible: boolean;
  onClose: () => void;
}

const DetailModal: React.FC<Prop> = ({ links, visible, onClose }) => {
  return (
    <Modal
      visible={visible}
      onCancel={onClose}
      footer={null}
      width="80%"
      title={"Travis Links (Newest to Oldest)"}
    >
      {links.map((link) => (
        <>
          <p>
            {link.sha_short} {link.commit_message}
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
